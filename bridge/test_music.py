"""Music selection and voice command tests; no provider or hardware access."""

import asyncio
import json
import unittest
from unittest.mock import patch

import bridge
import music


class MusicSearchTest(unittest.TestCase):
    def test_bundled_music_runtime_is_ready(self):
        self.assertIsNone(bridge.music_setup_problem())

    def test_picks_requested_title_and_artist_over_unrelated_result(self):
        payload = {"entries": [
            {"id": "a", "title": "Random Song", "uploader": "Someone", "url": "https://a"},
            {"id": "b", "title": "Blue Sky", "artist": "Luna", "url": "https://b"},
        ]}
        class FakeYDL:
            def __init__(self, _): pass
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def extract_info(self, *_args, **_kwargs): return payload
        with patch("yt_dlp.YoutubeDL", FakeYDL):
            track = music.search_track("Blue Sky Luna")
        self.assertEqual(track.id, "b")
        self.assertEqual(track.stream_url, "https://b")

    def test_does_not_claim_wrong_song(self):
        payload = {"entries": [
            {"id": "b", "title": "Random Song", "uploader": "Someone", "url": "https://b"},
        ]}
        class FakeYDL:
            def __init__(self, _): pass
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def extract_info(self, *_args, **_kwargs): return payload
        with patch("yt_dlp.YoutubeDL", FakeYDL):
            with self.assertRaisesRegex(music.MusicError, "Không tìm thấy bài phù hợp"):
                music.search_track("Blue Sky Luna")

    def test_clean_track_title_removes_clickbait_and_noisy_tags(self):
        cases = [
            ("Sơn Tùng M-TP | TIẾN LÊN VIỆT NAM ƠI! | OFFICIAL MUSIC VIDEO", "Sơn Tùng M-TP - TIẾN LÊN VIỆT NAM ƠI!"),
            ("Đi Về Nhà - Đen x JustaTee (Official Music Video)", "Đi Về Nhà - Đen x JustaTee"),
            ("Cháu Yêu Bà - Nhạc Thiếu Nhi Sôi Động Cho Bé Ăn Ngon [MV 4K]", "Cháu Yêu Bà"),
            ("Shape of You (Official Music Video)", "Shape of You"),
            ("BẬT TÌNH YÊU LÊN - HÒA MINZY x TĂNG DUY TÂN | OFFICIAL MUSIC VIDEO", "BẬT TÌNH YÊU LÊN - HÒA MINZY x TĂNG DUY TÂN"),
        ]
        for raw, expected in cases:
            cleaned = music.clean_track_title(raw)
            self.assertEqual(cleaned, expected)


class MusicVoiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_search_does_not_claim_music_started_before_playback(self):
        class Device:
            def __init__(self):
                self.sent = []

            async def send(self, value):
                self.sent.append(json.loads(value))

        device = Device()
        controller = bridge.MusicController(device, None, None, "session", 1,
                                            {"output_frames": 0})
        track = music.Track("b", "Blue Sky", "Luna")
        async def frames(_track, frame_bytes):
            yield b'x' * frame_bytes
        with patch.object(music, "search_track", return_value=track), patch.object(music, "pcm_frames", side_effect=frames):
            found = await controller.prepare("Blue Sky")
        self.assertEqual(found, track)
        self.assertIsNotNone(controller.first_frame)
        self.assertEqual(device.sent, [])
        await controller.stop()

    async def test_failed_search_restores_non_music_state(self):
        class Device:
            def __init__(self):
                self.sent = []

            async def send(self, value):
                self.sent.append(json.loads(value))

        device = Device()
        controller = bridge.MusicController(device, None, None, "session", 1,
                                            {"output_frames": 0})
        with patch.object(music, "search_track", side_effect=music.MusicError("missing")):
            with self.assertRaises(music.MusicError):
                await controller.prepare("missing")
        self.assertEqual(device.sent, [])

    async def test_unplayable_result_is_not_reported_ready(self):
        class Device:
            async def send(self, value):
                pass
        async def empty_frames(*args, **kwargs):
            if False:
                yield b''
        controller = bridge.MusicController(Device(), None, None, "s", 1, {})
        with patch.object(music, "search_track", return_value=music.Track("x", "X", "Y")), patch.object(music, "pcm_frames", side_effect=empty_frames):
            with self.assertRaises(music.MusicError):
                await controller.prepare("X")
        self.assertIsNone(controller.pending)
        self.assertIsNone(controller.prepared_stream)

    async def test_output_transcription_sets_emotion_without_tool_call(self):
        class Gemini:
            def __init__(self):
                self.sent = []

            def __aiter__(self):
                async def events():
                    yield json.dumps({"serverContent": {
                        "outputTranscription": {"text": "Mình yêu bạn!"}
                    }})
                    yield json.dumps({"serverContent": {"turnComplete": True}})
                return events()

            async def send(self, value):
                self.sent.append(json.loads(value))

        class Device:
            def __init__(self):
                self.sent = []

            async def send(self, value):
                self.sent.append(json.loads(value))

        gemini, device = Gemini(), Device()
        await bridge.gemini_output(
            gemini, device, None, None, "session", 1, {"gemini_content_seen": False},
            bridge.new_speech_state(), one_turn=True)
        self.assertEqual(device.sent[0]["type"], "llm")
        self.assertEqual(device.sent[0]["emotion"], "loving")

    async def test_track_pcm_reaches_robot_as_opus_and_stops(self):
        class Device:
            def __init__(self):
                self.sent = []

            async def send(self, value):
                self.sent.append(value)

        class Codec:
            def encode(self, _encoder, pcm):
                self.pcm = pcm
                return b"opus"

        async def frames(_track, frame_bytes):
            yield bytes(frame_bytes)
            yield bytes(frame_bytes)

        device, codec = Device(), Codec()
        controller = bridge.MusicController(device, None, codec, "session", 1,
                                            {"output_frames": 0})
        asked_after_music = []

        async def ask_after_music(track):
            asked_after_music.append(track)
            self.assertEqual(json.loads(device.sent[-1])["state"], "stop")

        controller.on_natural_end = ask_after_music
        controller.pending = music.Track("b", "Blue Sky", "Luna")
        with patch.object(music, "pcm_frames", side_effect=frames):
            await controller.start_pending()
            playback_task = controller.task
            await asyncio.wait_for(playback_task, 2)
        self.assertEqual(json.loads(device.sent[0])["type"], "music")
        self.assertEqual(sum(message == b"opus" for message in device.sent), 2)
        self.assertEqual(json.loads(device.sent[-1])["state"], "stop")
        self.assertEqual(asked_after_music, [music.Track("b", "Blue Sky", "Luna")])
        self.assertIsNone(controller.task)

    async def test_music_events_share_token_and_report_progress(self):
        class Device:
            def __init__(self): self.sent = []
            async def send(self, value): self.sent.append(value)
        class Codec:
            def encode(self, _encoder, _frame): return b"opus"
        async def frames(_track, frame_bytes):
            for _ in range(38):
                yield bytes(frame_bytes)

        device = Device()
        controller = bridge.MusicController(device, None, Codec(), "session", 1,
                                            {"output_frames": 0})
        controller.pending = music.Track("song", "Blue Sky", "Luna", duration=5.0)
        with patch.object(music, "pcm_frames", side_effect=frames):
            await controller.start_pending()
            if controller.task is not None:
                await controller.task

        events = [json.loads(value) for value in device.sent if isinstance(value, str)]
        music_events = [event for event in events if event.get("type") == "music"]
        self.assertEqual(music_events[0]["state"], "start")
        self.assertEqual(music_events[0]["title"], "Blue Sky")
        self.assertEqual(music_events[0]["artist"], "Luna")
        self.assertEqual(music_events[0]["duration_ms"], 5000)
        tokens = {event.get("playback_token") for event in music_events}
        self.assertEqual(len(tokens), 1)
        self.assertNotIn(None, tokens)
        progress = [event for event in music_events if event["state"] == "progress"]
        self.assertTrue(progress)
        self.assertTrue(all(0 <= event["position_ms"] <= 5000 for event in progress))
        self.assertEqual(music_events[-1]["state"], "stop")

    async def test_cover_failure_does_not_stop_music(self):
        class Device:
            def __init__(self): self.sent = []
            async def send(self, value): self.sent.append(value)
        class Codec:
            def encode(self, _encoder, _frame): return b"opus"
        async def frames(_track, frame_bytes):
            yield bytes(frame_bytes)
            yield bytes(frame_bytes)

        device = Device()
        controller = bridge.MusicController(device, None, Codec(), "session", 1,
                                            {"output_frames": 0})
        controller.pending = music.Track(
            "song", "Blue Sky", "Luna", thumbnail_url="https://img/cover.jpg", duration=2.0)
        with patch.object(music, "pcm_frames", side_effect=frames), \
             patch.object(bridge.learning_image, "_read_url", side_effect=OSError("offline")) as read:
            await controller.start_pending()
            if controller.task is not None:
                await controller.task
        read.assert_called_once()
        self.assertGreater(sum(value == b"opus" for value in device.sent), 0)
        states = [json.loads(value)["state"] for value in device.sent
                  if isinstance(value, str) and json.loads(value).get("type") == "music"]
        self.assertEqual(states[0], "start")
        self.assertEqual(states[-1], "stop")

    async def test_cover_event_includes_accent_color(self):
        class Device:
            def __init__(self): self.sent = []
            async def send(self, value): self.sent.append(value)
        class Codec:
            def encode(self, _encoder, _frame): return b"opus"
        async def frames(_track, frame_bytes):
            yield bytes(frame_bytes)
            yield bytes(frame_bytes)

        device = Device()
        controller = bridge.MusicController(device, None, Codec(), "session", 1,
                                            {"output_frames": 0})
        controller.pending = music.Track(
            "song", "Blue Sky", "Luna", thumbnail_url="https://img/cover.jpg", duration=2.0)
        with patch.object(music, "pcm_frames", side_effect=frames), \
             patch.object(bridge.learning_image, "_read_url", return_value=b"imgdata"), \
             patch.object(bridge.learning_image, "make_small_png_with_accent", return_value=(b"\x89PNG\r\n\x1a\nfake", "#FF5722")):
            await controller.start_pending()
            if controller.task is not None:
                await controller.task
            if controller.cover_task is not None:
                await controller.cover_task
        cover_events = [json.loads(v) for v in device.sent if isinstance(v, str) and json.loads(v).get("state") == "cover"]
        self.assertEqual(len(cover_events), 1)
        self.assertEqual(cover_events[0]["accent_color"], "#FF5722")

    async def test_progress_stops_with_playback(self):
        class Device:
            def __init__(self): self.sent = []
            async def send(self, value): self.sent.append(value)
        class Codec:
            def encode(self, _encoder, _frame): return b"opus"
        async def frames(_track, frame_bytes):
            for _ in range(36):
                yield bytes(frame_bytes)

        device = Device()
        controller = bridge.MusicController(device, None, Codec(), "session", 1,
                                            {"output_frames": 0})
        controller.pending = music.Track("song", "Blue Sky", "Luna", duration=3.0)
        with patch.object(music, "pcm_frames", side_effect=frames):
            await controller.start_pending()
            if controller.task is not None:
                await controller.task
        count_at_stop = len(device.sent)
        await asyncio.sleep(0.05)
        self.assertEqual(len(device.sent), count_at_stop)
        states = [json.loads(value)["state"] for value in device.sent
                  if isinstance(value, str) and json.loads(value).get("type") == "music"]
        self.assertIn("progress", states)
        self.assertEqual(states[-1], "stop")

    async def test_sender_failure_never_reports_playback_ready(self):
        class Device:
            async def send(self, value):
                if isinstance(value, bytes):
                    raise OSError("speaker connection lost")
        class Codec:
            def encode(self, encoder, frame):
                return b"opus"
        async def frames(*args, **kwargs):
            yield b"\0" * 2880
        controller = bridge.MusicController(Device(), None, Codec(), "s", 1, {"output_frames": 0})
        controller.pending = music.Track("x", "X", "Y")
        with patch.object(music, "pcm_frames", side_effect=frames):
            with self.assertRaises(music.MusicError):
                await asyncio.wait_for(controller.start_pending(), 4)
        self.assertFalse(controller.playback_ready.is_set())
        self.assertFalse(controller.is_active())

    async def test_decode_failure_after_start_reports_failure(self):
        class Device:
            async def send(self, value):
                pass
        class Codec:
            def encode(self, encoder, frame):
                return b"opus"
        async def frames(*args, **kwargs):
            yield b"\0" * 2880
            raise music.MusicError("stream ended unexpectedly")
        controller = bridge.MusicController(Device(), None, Codec(), "s", 1, {"output_frames": 0})
        failures = []
        async def failure(message):
            failures.append(message)
        controller.on_failure = failure
        controller.pending = music.Track("x", "X", "Y")
        with patch.object(music, "pcm_frames", side_effect=frames):
            await controller.start_pending()
            if controller.task is not None:
                await controller.task
        self.assertEqual(len(failures), 1)
        self.assertFalse(controller.is_active())

    async def test_play_song_confirmation_finishes_before_music_starts(self):
        class Gemini:
            def __init__(self):
                self.sent = []

            def __aiter__(self):
                async def events():
                    yield json.dumps({"toolCall": {"functionCalls": [
                        {"id": "one", "name": "play_song", "args": {"query": "Blue Sky"}}
                    ]}})
                    self.started_after_tool = controller.started
                    yield json.dumps({"serverContent": {
                        "outputTranscription": {"text": "Wisio tìm thấy bài Blue Sky rồi nè!"},
                        "modelTurn": {"parts": [{"inlineData": {"data": "AAAA"}}]}
                    }})
                    self.started_during_confirmation = controller.started
                    yield json.dumps({"serverContent": {"turnComplete": True}})
                return events()

            async def send(self, value):
                self.sent.append(json.loads(value))

        class Music:
            def __init__(self):
                self.started = False
                self.pending = None

            async def prepare(self, query):
                self.query = query
                self.pending = music.Track("b", "Blue Sky", "Luna")
                return self.pending

            async def schedule_pending(self):
                self.started = True

            async def start_pending(self):
                self.started = True
                self.pending = None

            def is_playing(self):
                return self.started

            def is_active(self):
                return self.started or self.pending is not None

            async def defer_for_speech(self):
                pass

        class Device:
            def __init__(self): self.sent = []
            async def send(self, value): self.sent.append(value)

        class Codec:
            def encode(self, _encoder, _pcm): return b"confirmation-opus"

        gemini, controller, device = Gemini(), Music(), Device()
        stats = {"gemini_content_seen": False, "output_frames": 0}
        await bridge.gemini_output(gemini, device, None, Codec(), "session", 1,
                                   stats, bridge.new_speech_state(), one_turn=True,
                                   music_controller=controller)
        self.assertEqual(controller.query, "Blue Sky")
        self.assertTrue(controller.started)
        self.assertFalse(gemini.started_after_tool)
        self.assertFalse(gemini.started_during_confirmation)
        self.assertIn(b"confirmation-opus", device.sent)
        self.assertEqual(gemini.sent[0]["toolResponse"]["functionResponses"][0]["id"], "one")

    async def test_unplayable_result_never_returns_success_instruction(self):
        class Gemini:
            def __init__(self): self.sent = []
            def __aiter__(self):
                async def events():
                    yield json.dumps({"toolCall": {"functionCalls": [{
                        "id": "bad", "name": "play_song", "args": {"query": "missing"},
                    }]}})
                    yield json.dumps({"serverContent": {"turnComplete": True}})
                return events()
            async def send(self, value): self.sent.append(json.loads(value))

        class Music:
            async def prepare(self, _query):
                raise music.MusicError("Không phát được")
            async def schedule_pending(self): pass
            def is_playing(self): return False
            def is_active(self): return False

        class Device:
            async def send(self, _value): pass

        gemini = Gemini()
        await bridge.gemini_output(
            gemini, Device(), None, None, "session", 1,
            {"gemini_content_seen": False}, bridge.new_speech_state(), one_turn=True,
            music_controller=Music(),
        )
        response = gemini.sent[0]["toolResponse"]["functionResponses"][0]["response"]
        self.assertEqual(response, {"error": "Không phát được"})
        self.assertNotIn("Found", json.dumps(response))

    async def test_pending_music_waits_for_requested_delay(self):
        controller = bridge.MusicController(None, None, None, "session", 1,
                                            {"output_frames": 0})
        controller.pending = music.Track("b", "Blue Sky", "Luna")
        started = asyncio.Event()

        async def start_pending():
            started.set()

        with patch.object(controller, "start_pending", side_effect=start_pending):
            await controller.schedule_pending(delay=0.05)
            await asyncio.sleep(0.01)
            self.assertFalse(started.is_set())
            await asyncio.wait_for(started.wait(), 0.2)

    async def test_speech_cancels_playing_music_and_queues_same_track(self):
        controller = bridge.MusicController(None, None, None, "session", 1,
                                            {"output_frames": 0})
        track = music.Track("b", "Blue Sky", "Luna")
        controller.current = track
        controller.task = asyncio.create_task(asyncio.sleep(60))
        await controller.defer_for_speech()
        self.assertIsNone(controller.task)
        self.assertIsNone(controller.current)
        self.assertEqual(controller.pending, track)


if __name__ == "__main__":
    unittest.main()
