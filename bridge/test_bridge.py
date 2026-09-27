"""Local protocol smoke test. Never contacts Google or a physical device."""

import asyncio
import base64
from contextlib import contextmanager
import io
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import threading
import urllib.request
import unittest
import socket
import shutil
import uuid
from unittest.mock import patch

import websockets

import bridge
import probe_gemini
import probe_recorded_live
import transcribe_mic


PY_OPUS = bridge.find_opus_library()


@contextmanager
def writable_test_dir():
    """Avoid Python 3.14's restrictive Windows ACL on TemporaryDirectory."""
    root = Path.cwd() / "test-tmp"
    root.mkdir(exist_ok=True)
    path = root / f"case-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


class BridgeTest(unittest.IsolatedAsyncioTestCase):
    def test_bridge_discovery_returns_current_lan_endpoint(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        stop = threading.Event()
        server = threading.Thread(
            target=bridge.serve_bridge_discovery,
            args=("192.168.1.25", stop, port),
            daemon=True,
        )
        server.start()
        stop.wait(0.05)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(1.0)
                client.sendto(b"WISIO_DISCOVER_V1", ("127.0.0.1", port))
                payload, _ = client.recvfrom(256)
            self.assertEqual(
                payload,
                b"WISIO_BRIDGE_V1 http://192.168.1.25:8003/xiaozhi/ota/",
            )
        finally:
            stop.set()
            server.join(timeout=1.0)

    def test_emotion_requires_clear_words_and_holds_strong_mood(self):
        self.assertIsNone(bridge.emotion_for_text("Mình sẽ giải thích cho bạn."))
        tracker = bridge.EmotionTracker()
        self.assertEqual(bridge.reaction_to_user_text("Đồ ngu, im đi!!!"), "surprised")
        self.assertIsNone(bridge.reaction_to_user_text("Mình chưa hiểu bài này."))
        self.assertEqual(tracker.update("Mình rất tiếc, chuyện này thật buồn.", now=10), "sad")
        self.assertIsNone(tracker.update("Nhưng cũng hay quá!", now=12))
        self.assertEqual(tracker.update("Bây giờ thì thật vui, chúc mừng nhé!", now=19), "happy")

    async def test_key_prompt_does_not_block_websocket_handshake(self):
        release = threading.Event()
        prompt_started = threading.Event()

        def prompt(_):
            prompt_started.set()
            release.wait(timeout=3)
            return "test-key"

        async def verify(_):
            return True

        async def handler(ws):
            await ws.send("accepted")

        key_ready = asyncio.Event()
        key_state = {"value": ""}
        with patch.object(bridge.getpass, "getpass", side_effect=prompt), patch.object(
            bridge, "verify_gemini_key", side_effect=verify
        ):
            async with websockets.serve(handler, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                task = asyncio.create_task(bridge.run_bridge("", key_state, key_ready))
                try:
                    self.assertTrue(await asyncio.to_thread(prompt_started.wait, 1))
                    async with asyncio.timeout(1):
                        async with websockets.connect(f"ws://127.0.0.1:{port}/") as ws:
                            self.assertEqual(await ws.recv(), "accepted")
                    release.set()
                    await asyncio.wait_for(key_ready.wait(), 1)
                    self.assertEqual(key_state["value"], "test-key")
                finally:
                    release.set()
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

    async def test_replay_probe_sends_recorded_audio_in_both_vad_modes(self):
        async def mock_gemini(ws):
            setup = json.loads(await ws.recv())
            detection = setup["setup"]["realtimeInputConfig"]["automaticActivityDetection"]
            await bridge.send_json(ws, {"setupComplete": {}})
            saw_audio = False
            async for raw in ws:
                realtime = json.loads(raw)["realtimeInput"]
                if "audio" in realtime:
                    saw_audio = bool(base64.b64decode(realtime["audio"]["data"]))
                if "activityEnd" in realtime or realtime.get("audioStreamEnd"):
                    self.assertTrue(saw_audio)
                    self.assertEqual("activityEnd" in realtime, bool(detection.get("disabled")))
                    await bridge.send_json(ws, {"serverContent": {
                        "modelTurn": {"parts": [{"inlineData": {"data": "YXVkaW8="}}]},
                        "turnComplete": True,
                    }})
                    return

        server = await websockets.serve(mock_gemini, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            with patch.object(probe_recorded_live, "GEMINI_ENDPOINT", f"ws://127.0.0.1:{port}/gemini"):
                for manual in (True, False):
                    self.assertTrue(await probe_recorded_live.trial("fake-key", [bytes(1920)], manual))
        finally:
            server.close()
            await server.wait_closed()

    async def test_transcription_probe_sends_wav_without_exposing_key(self):
        with writable_test_dir() as temp_dir:
            wav_path = os.path.join(temp_dir, "mic.wav")
            import wave
            with wave.open(wav_path, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(bytes(320))
            reply = io.BytesIO(b'{"candidates":[{"content":{"parts":[{"text":"Xin chao"}]}}]}')
            with patch.object(transcribe_mic, "WAV_PATH", Path(wav_path)), \
                 patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}), \
                 patch.object(transcribe_mic, "urlopen", return_value=reply) as urlopen, \
                 patch("builtins.print") as printed:
                transcribe_mic.main()
                request = urlopen.call_args.args[0]
                self.assertEqual(request.get_header("X-goog-api-key"), "fake-key")
                payload = json.loads(request.data)
                self.assertEqual(payload["contents"][0]["parts"][1]["inlineData"]["mimeType"], "audio/wav")
                self.assertTrue(any("Xin chao" in str(call) for call in printed.call_args_list))

    async def test_diagnostic_captures_mic_and_probes_speaker(self):
        codec = bridge.Opus(PY_OPUS)
        mic_encoder = codec.encoder(16000)
        speaker_decoder = codec.decoder(24000)
        gemini_connections = []

        async def mock_gemini(ws):
            gemini_connections.append(ws)
            setup = json.loads(await ws.recv())
            self.assertEqual(
                setup["setup"]["generationConfig"]["speechConfig"]["voiceConfig"]
                ["prebuiltVoiceConfig"]["voiceName"], bridge.GEMINI_VOICE
            )
            await bridge.send_json(ws, {"setupComplete": {}})
            async for raw in ws:
                event = json.loads(raw)
                if "clientContent" in event:
                    self.assertEqual(len(gemini_connections), 2)
                    self.assertIn("speaker test", event["clientContent"]["turns"][0]["parts"][0]["text"])
                    # Gemini JSON may arrive in a binary WebSocket frame.
                    await ws.send(json.dumps({"serverContent": {
                        "modelTurn": {"parts": [{"inlineData": {
                            "data": base64.b64encode(bytes(bridge.OUTPUT_SAMPLES * 2)).decode()
                        }}]},
                        "turnComplete": True,
                    }}).encode("utf-8"))

        mock_server = await websockets.serve(mock_gemini, "127.0.0.1", 0)
        mock_port = mock_server.sockets[0].getsockname()[1]
        device_server = await websockets.serve(
            lambda ws: bridge.handle_device(ws, "fake-key", codec), "127.0.0.1", 0
        )
        device_port = device_server.sockets[0].getsockname()[1]
        try:
            with writable_test_dir() as temp_dir, \
                 patch.dict(os.environ, {"XIAOZHI_DIAGNOSTIC": "1"}), \
                 patch.object(bridge, "GEMINI_ENDPOINT", f"ws://127.0.0.1:{mock_port}/gemini"), \
                 patch.object(bridge, "MIC_STREAM_PAUSE_SECONDS", 0.05), \
                 patch.object(bridge, "DIAGNOSTIC_WAIT_SECONDS", 0.05), \
                 patch.object(bridge, "DIAGNOSTIC_REPLY_WAV", os.path.join(temp_dir, "reply.wav")), \
                 patch.object(bridge, "DIAGNOSTIC_WAV", os.path.join(temp_dir, "mic.wav")):
                async with websockets.connect(f"ws://127.0.0.1:{device_port}/xiaozhi/v1/") as device:
                    await bridge.send_json(device, {
                        "type": "hello", "transport": "websocket", "version": 1,
                        "audio_params": {"sample_rate": 16000},
                    })
                    await asyncio.wait_for(device.recv(), 3)
                    pcm = b"".join(struct.pack("<h", round(2500 * math.sin(2 * math.pi * 440 * n / 16000))) for n in range(960))
                    import ctypes
                    samples = (ctypes.c_int16 * 960).from_buffer_copy(pcm)
                    packet_buf = ctypes.create_string_buffer(4000)
                    packet_len = codec.lib.opus_encode(mic_encoder, samples, 960, packet_buf, 4000)
                    await device.send(packet_buf.raw[:packet_len])
                    saw_start = False
                    saw_audio = False
                    while True:
                        message = await asyncio.wait_for(device.recv(), 4)
                        if isinstance(message, bytes):
                            self.assertEqual(len(codec.decode(speaker_decoder, message)), bridge.OUTPUT_SAMPLES * 2)
                            saw_audio = True
                        else:
                            event = json.loads(message)
                            if event.get("type") == "tts" and event.get("state") == "start":
                                saw_start = True
                            if event.get("type") == "tts" and event.get("state") == "stop":
                                break
                    self.assertTrue(saw_start and saw_audio)
                    self.assertEqual(len(gemini_connections), 2)
                import wave
                with wave.open(os.path.join(temp_dir, "mic.wav"), "rb") as wav:
                    self.assertEqual(wav.getframerate(), 16000)
                    self.assertGreater(wav.getnframes(), 0)
                with wave.open(os.path.join(temp_dir, "reply.wav"), "rb") as wav:
                    self.assertEqual(wav.getframerate(), 24000)
                    self.assertEqual(wav.getnframes(), bridge.OUTPUT_SAMPLES)
        finally:
            mock_server.close()
            device_server.close()
            await mock_server.wait_closed()
            await device_server.wait_closed()
            codec.lib.opus_encoder_destroy(mic_encoder)
            codec.lib.opus_decoder_destroy(speaker_decoder)

    async def test_text_probe_separates_gemini_from_robot(self):
        async def mock_gemini(ws):
            setup = json.loads(await ws.recv())
            self.assertEqual(setup["setup"]["model"], "models/gemini-3.8-live")
            await bridge.send_json(ws, {"setupComplete": {}})
            prompt = json.loads(await ws.recv())
            self.assertTrue(prompt["clientContent"]["turnComplete"])
            await bridge.send_json(ws, {"serverContent": {
                "modelTurn": {"parts": [{"inlineData": {"data": "YXVkaW8="}}]},
                "turnComplete": True,
            }})

        server = await websockets.serve(mock_gemini, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}), \
                 patch.object(probe_gemini, "GEMINI_ENDPOINT", f"ws://127.0.0.1:{port}/gemini"), \
                 patch("builtins.print") as printed:
                await probe_gemini.main()
                self.assertTrue(any("Gemini can speak" in str(call) for call in printed.call_args_list))
        finally:
            server.close()
            await server.wait_closed()

    async def test_key_checked_before_robot_connects(self):
        async def mock_gemini(ws):
            await ws.recv()
            if "invalid" in ws.request.path:
                await ws.close(code=1007, reason="API key not valid. Please pass a valid API key.")
            else:
                await bridge.send_json(ws, {"setupComplete": {}})

        server = await websockets.serve(mock_gemini, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            with patch.object(bridge, "GEMINI_ENDPOINT", f"ws://127.0.0.1:{port}/gemini"):
                self.assertFalse(await bridge.verify_gemini_key("invalid"))
                self.assertTrue(await bridge.verify_gemini_key("valid"))
                real_connect = websockets.connect
                attempts = 0

                def slow_first_handshake(*args, **kwargs):
                    nonlocal attempts
                    attempts += 1
                    self.assertEqual(kwargs["family"], bridge.socket.AF_INET)
                    self.assertIsNone(kwargs["proxy"])
                    if attempts == 1:
                        raise TimeoutError("timed out during opening handshake")
                    return real_connect(*args, **kwargs)

                with patch.object(bridge.websockets, "connect", side_effect=slow_first_handshake):
                    self.assertTrue(await bridge.verify_gemini_key("valid"))
                self.assertEqual(attempts, 2)
        finally:
            server.close()
            await server.wait_closed()

    async def test_v1_audio_packet(self):
        packet = b"opus"
        self.assertEqual(bridge.unpack_audio(bridge.pack_audio(packet, 1), 1), packet)

    async def test_audio_burst_waits_for_speaking_then_is_paced(self):
        sent = []
        class Device:
            async def send(self, message):
                sent.append((asyncio.get_running_loop().time(), message))
        class Codec:
            def encode(self, encoder, pcm):
                return b"opus"
        async def responses():
            yield json.dumps({"serverContent": {
                "modelTurn": {"parts": [{"inlineData": {
                    "data": base64.b64encode(bytes(
                        bridge.OUTPUT_SAMPLES * 2 * (bridge.PLAYBACK_LEAD_FRAMES + 1)
                    )).decode()
                }}]}, "turnComplete": True}}).encode()
        stats = {"output_frames": 0, "gemini_content_seen": False}
        await bridge.gemini_output(responses(), Device(), None, Codec(), "test", 1,
                                   stats, bridge.new_speech_state())
        times = [at for at, message in sent if isinstance(message, bytes)]
        self.assertEqual(len(times), bridge.PLAYBACK_LEAD_FRAMES + 1)
        start_at = next(at for at, message in sent if isinstance(message, str) and
                        json.loads(message).get("state") == "start")
        self.assertGreaterEqual(times[0] - start_at, bridge.SPEAKING_SETTLE_SECONDS - 0.02)
        self.assertLess(times[bridge.PLAYBACK_LEAD_FRAMES - 1] - times[0], 0.05)
        self.assertGreaterEqual(
            times[bridge.PLAYBACK_LEAD_FRAMES] - times[bridge.PLAYBACK_LEAD_FRAMES - 1], 0.05)
        self.assertEqual(json.loads(sent[-1][1])["state"], "stop")
        self.assertGreaterEqual(
            sent[-1][0] - times[-1],
            (bridge.PLAYBACK_LEAD_FRAMES + bridge.PLAYBACK_TAIL_FRAMES) * bridge.FRAME_MS / 1000 - 0.03,
        )

    async def test_locked_diagnostic_reply_uses_another_filename(self):
        with writable_test_dir() as temp_dir:
            destination = os.path.join(temp_dir, "reply.wav")
            real_wave_open = bridge.wave.open

            def locked_first_path(path, mode):
                if path == destination:
                    raise PermissionError("The file is open in a player")
                return real_wave_open(path, mode)

            with patch.object(bridge, "DIAGNOSTIC_REPLY_WAV", destination), \
                 patch.object(bridge.wave, "open", side_effect=locked_first_path):
                saved = bridge.save_diagnostic_reply(bytes(bridge.OUTPUT_SAMPLES * 2))

            self.assertIsNotNone(saved)
            self.assertNotEqual(saved, destination)
            self.assertTrue(os.path.isfile(saved))
            with real_wave_open(saved, "rb") as wav:
                self.assertEqual(wav.getnframes(), bridge.OUTPUT_SAMPLES)

    async def test_interruption_discards_queued_audio(self):
        sent = []
        class Device:
            async def send(self, message):
                sent.append(message)
        class Codec:
            def encode(self, encoder, pcm):
                return b"opus"
        async def responses():
            yield json.dumps({"serverContent": {"modelTurn": {"parts": [{"inlineData": {
                "data": base64.b64encode(bytes(bridge.OUTPUT_SAMPLES * 2 * 20)).decode()
            }}]}}})
            await asyncio.sleep(0.28)
            yield json.dumps({"serverContent": {"interrupted": True}})
        stats = {"output_frames": 0, "gemini_content_seen": False}
        await bridge.gemini_output(responses(), Device(), None, Codec(), "test", 1,
                                   stats, bridge.new_speech_state())
        self.assertGreater(stats["output_frames"], 0)
        self.assertLess(stats["output_frames"], 20)
        self.assertEqual(json.loads(sent[-1])["state"], "stop")
        count = len(sent)
        await asyncio.sleep(0.1)
        self.assertEqual(len(sent), count)

    async def test_playback_reports_upstream_gap(self):
        class Device:
            async def send(self, message):
                pass
        class Codec:
            def encode(self, encoder, pcm):
                return b"opus"
        playback = bridge.PacedPlayback(Device(), None, Codec(), "test", 1,
                                        {"output_frames": 0})
        for _ in range(bridge.PLAYBACK_LEAD_FRAMES):
            playback.put(bytes(bridge.OUTPUT_SAMPLES * 2))
        await asyncio.sleep(0.35)
        playback.put(bytes(bridge.OUTPUT_SAMPLES * 2))
        await playback.finish()
        self.assertEqual(playback.sent_frames, bridge.PLAYBACK_LEAD_FRAMES + 1)
        self.assertGreater(playback.underruns, 0)

    async def test_gemini_close_releases_listening_device(self):
        codec = bridge.Opus(PY_OPUS)

        async def mock_gemini(ws):
            await ws.recv()
            await bridge.send_json(ws, {"setupComplete": {}})
            await ws.close(code=1000)

        mock_server = await websockets.serve(mock_gemini, "127.0.0.1", 0)
        mock_port = mock_server.sockets[0].getsockname()[1]
        device_server = await websockets.serve(
            lambda ws: bridge.handle_device(ws, "fake-key", codec), "127.0.0.1", 0
        )
        device_port = device_server.sockets[0].getsockname()[1]
        try:
            with patch.object(bridge, "GEMINI_ENDPOINT", f"ws://127.0.0.1:{mock_port}/gemini"):
                async with websockets.connect(f"ws://127.0.0.1:{device_port}/xiaozhi/v1/") as device:
                    await bridge.send_json(device, {
                        "type": "hello", "transport": "websocket", "version": 1,
                        "audio_params": {"sample_rate": 16000},
                    })
                    self.assertEqual(json.loads(await asyncio.wait_for(device.recv(), 3))["type"], "hello")
                    with self.assertRaises(websockets.exceptions.ConnectionClosedError):
                        await asyncio.wait_for(device.recv(), 3)
        finally:
            mock_server.close()
            device_server.close()
            await mock_server.wait_closed()
            await device_server.wait_closed()

    async def test_brief_background_spikes_do_not_delay_speech_end(self):
        state = bridge.new_speech_state()
        self.assertFalse(bridge.update_speech_state(state, 600, 0.0))
        for index in range(1, 35):
            level = 360 if index == 6 else 180
            self.assertFalse(bridge.update_speech_state(state, level, index * 0.06))
        self.assertTrue(bridge.update_speech_state(state, 180, 36 * 0.06))

    async def test_thinking_pause_does_not_cut_the_sentence(self):
        state = bridge.new_speech_state()
        self.assertFalse(bridge.update_speech_state(state, 650, 0.0))
        for index in range(1, 11):
            self.assertFalse(bridge.update_speech_state(state, 150, index * 0.06))
        self.assertFalse(bridge.update_speech_state(state, 560, 0.66))
        for index in range(12, 46):
            self.assertFalse(bridge.update_speech_state(state, 150, index * 0.06))
        self.assertTrue(bridge.update_speech_state(state, 150, 47 * 0.06))

    async def test_vietnam_time_is_exact_utc_plus_seven(self):
        utc = bridge.datetime(2026, 9, 23, 1, 2, 3, tzinfo=bridge.timezone.utc)
        result = bridge.vietnam_time_result(utc)
        self.assertEqual(result["local_date"], "23/09/2026")
        self.assertEqual(result["local_time"], "08:02:03")
        self.assertEqual(result["utc_offset"], "+07:00")

    async def test_memory_survives_reload_and_rejects_secrets(self):
        path = Path.cwd() / "_wisio_test_memory.json"
        try:
            path.unlink(missing_ok=True)
            memory = bridge.PersistentMemory(path)
            self.assertTrue(memory.remember("Bạn An thích học từ vựng về động vật.")["saved"])
            self.assertFalse(memory.remember("API key là abc123")["saved"])
            reloaded = bridge.PersistentMemory(path)
            self.assertIn("Bạn An thích học từ vựng về động vật.", reloaded.prompt_context())
            self.assertEqual(reloaded.forget("động vật")["deleted"], 1)
            self.assertNotIn("động vật", bridge.PersistentMemory(path).prompt_context())
        finally:
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".tmp").unlink(missing_ok=True)

    async def test_sustained_speech_does_not_end_turn(self):
        state = bridge.new_speech_state()
        self.assertFalse(bridge.update_speech_state(state, 600, 0.0))
        for index in range(1, 40):
            level = 500 if index % 4 == 0 else 180
            self.assertFalse(bridge.update_speech_state(state, level, index * 0.06))

    async def test_microphone_gain_avoids_clipping_and_recovers(self):
        state = bridge.new_speech_state()
        loud = struct.pack("<hhh", 23000, -23000, 1000)
        processed = bridge.boost_pcm(loud, state)
        self.assertLessEqual(max(map(abs, struct.unpack("<hhh", processed))), 30000)
        reduced_gain = state["mic_gain"]
        self.assertLess(reduced_gain, bridge.MIC_GAIN)
        quiet = struct.pack("<hhh", 100, -100, 0)
        processed = bridge.boost_pcm(quiet, state)
        self.assertGreater(state["mic_gain"], reduced_gain)
        self.assertLessEqual(max(map(abs, struct.unpack("<hhh", processed))), 30000)

    async def test_ota_and_audio_round_trip(self):
        codec = bridge.Opus(PY_OPUS)
        mic_encoder = codec.encoder(16000)
        speaker_decoder = codec.decoder(24000)
        mock_received_audio = asyncio.Event()

        async def mock_gemini(ws):
            setup = json.loads(await ws.recv())
            self.assertEqual(setup["setup"]["model"], "models/gemini-3.8-live")
            self.assertEqual(setup["setup"]["generationConfig"]["responseModalities"], ["AUDIO"])
            detection = setup["setup"]["realtimeInputConfig"]["automaticActivityDetection"]
            self.assertTrue(detection["disabled"])
            instruction = setup["setup"]["systemInstruction"]["parts"][0]["text"]
            self.assertIn("complete the entire requested range", instruction)
            self.assertIn("RESPOND IN VIETNAMESE BY DEFAULT", instruction)
            self.assertIn("only when the user speaks to you in English", instruction)
            self.assertIn("at most three or four short spoken sentences", instruction)
            self.assertIn("Asia/Ho_Chi_Minh", instruction)
            self.assertIn("interactive CEFR A1-B2 English tutor", instruction)
            self.assertIn("OWNER-PROVIDED PRODUCT BEHAVIOR SPECIFICATION", instruction)
            self.assertIn("BẠN LÀ AI? (IDENTITY)", instruction)
            self.assertIn("CÂU HỎI CHỦ ĐỘNG PHẢI CỤ THỂ VÀ CÓ ÍCH", instruction)
            self.assertIn("sleep quality, hydration, eye breaks, posture", instruction)
            self.assertIn("not a chatbot", instruction)
            self.assertIn("asking one friendly, specific question at a time", instruction)
            self.assertIn("persistent local memory tools", instruction)
            self.assertNotIn("responseModalities", setup["setup"])
            await bridge.send_json(ws, {"setupComplete": {}})
            got_audio = False
            audio_times = []
            activity_started = False
            async for raw in ws:
                event = json.loads(raw)
                realtime = event.get("realtimeInput", {})
                if "activityStart" in realtime:
                    self.assertFalse(activity_started)
                    activity_started = True
                if "audio" in realtime:
                    self.assertTrue(activity_started)
                    audio_times.append(asyncio.get_running_loop().time())
                    pcm = base64.b64decode(realtime["audio"]["data"])
                    self.assertEqual(len(pcm), 16000 * 2 * 60 // 1000)
                    self.assertGreater(bridge.microphone_level(pcm), 1500)
                    mock_received_audio.set()
                    got_audio = True
                if "activityEnd" in realtime:
                    self.assertTrue(activity_started)
                    self.assertTrue(got_audio)
                    self.assertEqual(len(audio_times), 7)
                    self.assertGreaterEqual(audio_times[1] - audio_times[0], 0.045)
                    self.assertGreaterEqual(audio_times[2] - audio_times[1], 0.045)
                    await bridge.send_json(ws, {"serverContent": {
                        "inputTranscription": {"text": "Hello"},
                        "outputTranscription": {"text": "Hi"},
                        "modelTurn": {"parts": [{"inlineData": {
                            "data": base64.b64encode(bytes(bridge.OUTPUT_SAMPLES * 2)).decode()
                        }}]},
                        "turnComplete": True,
                    }})

        mock_server = await websockets.serve(mock_gemini, "127.0.0.1", 0)
        mock_port = mock_server.sockets[0].getsockname()[1]
        device_server = await websockets.serve(
            lambda ws: bridge.handle_device(ws, "fake-key", codec), "127.0.0.1", 0
        )
        device_port = device_server.sockets[0].getsockname()[1]
        try:
            with patch.object(bridge, "GEMINI_ENDPOINT", f"ws://127.0.0.1:{mock_port}/gemini"):
                async with websockets.connect(f"ws://127.0.0.1:{device_port}/xiaozhi/v1/") as device:
                    await bridge.send_json(device, {
                        "type": "hello", "transport": "websocket", "version": 1,
                        "audio_params": {"sample_rate": 16000},
                    })
                    hello = json.loads(await asyncio.wait_for(device.recv(), 3))
                    self.assertEqual(hello["audio_params"]["sample_rate"], 24000)
                    pcm = b"".join(struct.pack("<h", round(6000 * math.sin(2 * math.pi * 440 * n / 16000))) for n in range(960))
                    encoded = codec.lib.opus_encode
                    # This input packet is 60 ms mono Opus at 16 kHz.
                    import ctypes
                    samples = (ctypes.c_int16 * 960).from_buffer_copy(pcm)
                    packet_buf = ctypes.create_string_buffer(4000)
                    packet_len = encoded(mic_encoder, samples, 960, packet_buf, 4000)
                    self.assertGreater(packet_len, 0)
                    for _ in range(7):
                        await device.send(bridge.pack_audio(packet_buf.raw[:packet_len], 1))
                    await asyncio.wait_for(mock_received_audio.wait(), 3)
                    events = []
                    while True:
                        message = await asyncio.wait_for(device.recv(), 3)
                        if isinstance(message, bytes):
                            decoded = codec.decode(speaker_decoder, bridge.unpack_audio(message, 1))
                            self.assertEqual(len(decoded), bridge.OUTPUT_SAMPLES * 2)
                            events.append("audio")
                        else:
                            event = json.loads(message)
                            events.append(event.get("state") or event.get("type"))
                            if event.get("type") == "tts" and event.get("state") == "stop":
                                break
                    self.assertIn("stt", events)
                    self.assertIn("start", events)
                    self.assertIn("audio", events)

            handler = bridge.make_ota_handler("192.168.100.7")
            from http.server import ThreadingHTTPServer
            import threading
            ota = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            ota_thread = threading.Thread(target=ota.serve_forever, daemon=True)
            ota_thread.start()
            try:
                port = ota.server_address[1]
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/xiaozhi/ota/") as response:
                    result = json.load(response)
                self.assertEqual(result["websocket"]["url"], "ws://192.168.100.7:8000/xiaozhi/v1/")
                self.assertEqual(result["server_time"]["timezone_offset"], 420)
                self.assertEqual(result["server_time"]["timezone"], "Asia/Ho_Chi_Minh")
            finally:
                ota.shutdown()
                ota.server_close()
        finally:
            mock_server.close()
            device_server.close()
            await mock_server.wait_closed()
            await device_server.wait_closed()
            codec.lib.opus_encoder_destroy(mic_encoder)
            codec.lib.opus_decoder_destroy(speaker_decoder)


if __name__ == "__main__":
    unittest.main()
