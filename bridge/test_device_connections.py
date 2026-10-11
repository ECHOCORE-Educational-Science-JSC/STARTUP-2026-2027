"""Device reconnects replace stale sessions without sharing speaker ownership."""

import asyncio
import base64
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import bridge


class DevicePeer:
    request = SimpleNamespace(path="/wisio/v1/")

    def __init__(self, device_uuid="device-one", boot_id=42, version=1):
        self.hello = {"type": "hello", "transport": "websocket", "version": version,
                      "audio_params": {"sample_rate": 16000}, "boot_id": boot_id,
                      "device_uuid": device_uuid, "wisio_id": "123"}
        self.close_code = None
        self.close_reason = ""
        self.messages = asyncio.Queue()
        self.sent = []
        self.changed = asyncio.Event()
        self.listening = asyncio.Event()
        self.closed = asyncio.Event()
        self.close_gate = None

    async def recv(self):
        return json.dumps(self.hello)

    async def send(self, data):
        self.sent.append(json.loads(data))
        self.changed.set()
        await asyncio.sleep(0)

    def __aiter__(self):
        async def stream():
            self.listening.set()
            while True:
                data = await self.messages.get()
                if data is None:
                    return
                yield data
        return stream()

    async def close(self, code=1000, reason=""):
        if self.close_code is None:
            self.close_code, self.close_reason = code, reason
        if self.close_gate is not None:
            await self.close_gate.wait()
        if not self.closed.is_set():
            self.closed.set()
            self.messages.put_nowait(None)

    async def wait_sent(self, predicate):
        while True:
            self.changed.clear()
            for item in self.sent:
                if predicate(item):
                    return item
            await self.changed.wait()


class GeminiPeer:
    def __init__(self):
        self.close_code = None
        self.close_reason = ""
        self.sent = []
        self.messages = asyncio.Queue()
        self.greeting_started = asyncio.Event()
        self.greeting_gate = None
        self.closed = asyncio.Event()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.close_code = 1000
        self.closed.set()

    async def recv(self):
        await asyncio.sleep(0)
        return json.dumps({"setupComplete": {}})

    async def send(self, data):
        event = json.loads(data)
        self.sent.append(event)
        if "clientContent" in event:
            self.greeting_started.set()
            if self.greeting_gate is not None:
                await self.greeting_gate.wait()
        await asyncio.sleep(0)

    def __aiter__(self):
        async def stream():
            while True:
                event = await self.messages.get()
                if event is None:
                    return
                yield json.dumps(event)
        return stream()


class Codec:
    def __init__(self):
        self.next_handle = 0
        self.destroyed = []
        self.before_destroy = lambda: None
        def destroy(handle):
            self.before_destroy()
            self.destroyed.append(handle)
        self.lib = SimpleNamespace(opus_decoder_destroy=destroy,
                                   opus_encoder_destroy=destroy)

    def decoder(self, *_args):
        self.next_handle += 1
        return self.next_handle

    encoder = decoder

    def decode(self, *_args):
        return bytes(bridge.INPUT_RATE * bridge.FRAME_MS // 1000 * 2)


class Memory:
    def prompt_context(self):
        return ""


class DeviceConnectionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.devices, self.tasks, self.geminis = [], [], []
        self.codec = Codec()
        self.background_live = set()
        self.session_stats = []
        self.next_greeting_gate = None

        def connect(_key):
            gemini = GeminiPeer()
            gemini.greeting_gate, self.next_greeting_gate = self.next_greeting_gate, None
            self.geminis.append(gemini)
            return gemini

        original_output, original_idle = bridge.gemini_output, bridge.proactive_idle_loop

        async def tracked_output(*args, **kwargs):
            self.session_stats.append(args[6])
            token = ("output", args[0])
            self.background_live.add(token)
            try:
                return await original_output(*args, **kwargs)
            finally:
                self.background_live.discard(token)

        async def tracked_idle(*args, **kwargs):
            token = ("idle", args[0])
            self.background_live.add(token)
            try:
                return await original_idle(*args, **kwargs)
            finally:
                self.background_live.discard(token)

        for patcher in (patch.object(bridge, "connect_gemini", side_effect=connect),
                        patch.object(bridge, "PersistentMemory", Memory),
                        patch.object(bridge.guardian_alert, "GuardianAlerter", return_value=
                                     SimpleNamespace(recipient="", ready=False)),
                        patch.object(bridge, "DEVICE_CONNECTIONS", {}, create=True),
                        patch.object(bridge, "gemini_output", side_effect=tracked_output),
                        patch.object(bridge, "proactive_idle_loop", side_effect=tracked_idle)):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def asyncTearDown(self):
        for device in self.devices:
            if device.close_gate is not None:
                device.close_gate.set()
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), 2)

    def start(self, device):
        self.devices.append(device)
        task = asyncio.create_task(bridge.handle_device(device, "fake-key", self.codec))
        self.tasks.append(task)
        return task

    async def ready(self, device):
        await asyncio.wait_for(device.listening.wait(), 2)

    async def test_same_uuid_reconnect_retires_old_session_and_keeps_new_usable(self):
        first, second = DevicePeer(), DevicePeer()
        old_task = self.start(first)
        await self.ready(first)
        old_gemini = self.geminis[0]
        new_task = self.start(second)
        await self.ready(second)
        self.assertTrue(old_task.done(), "old same-device handler must finish before new session operates")
        self.assertEqual(first.close_code, 1001)
        self.assertTrue(old_gemini.closed.is_set())
        self.assertNotIn(("output", old_gemini), self.background_live)
        self.assertNotIn(("idle", old_gemini), self.background_live)
        self.assertEqual(len(self.codec.destroyed), 2)
        self.assertFalse(new_task.done())
        self.geminis[-1].messages.put_nowait({"serverContent": {
            "outputTranscription": {"text": "Phiên mới hoạt động."}}})
        await asyncio.wait_for(second.wait_sent(lambda item: item.get("text") == "Phiên mới hoạt động."), 1)
        self.assertEqual(sum("clientContent" in event for peer in self.geminis for event in peer.sent), 2)

    async def test_invalid_replacement_hello_does_not_evict_healthy_session(self):
        first, invalid = DevicePeer(), DevicePeer(version=9)
        old_task = self.start(first)
        await self.ready(first)
        await asyncio.wait_for(self.start(invalid), 1)
        self.assertFalse(old_task.done())
        self.assertIsNone(first.close_code)
        self.assertEqual(len(self.geminis), 1)

    async def test_different_and_unknown_device_uuids_remain_independent(self):
        for identity in ("device-one", "device-two", "", ""):
            device = DevicePeer(identity)
            self.start(device)
            await self.ready(device)
        self.assertEqual(len(self.geminis), 4)
        self.assertTrue(all(not task.done() for task in self.tasks))

    async def test_new_boot_id_preserves_legitimate_startup_greeting(self):
        first, second = DevicePeer(boot_id=42), DevicePeer(boot_id=43)
        self.start(first)
        await self.ready(first)
        self.start(second)
        await self.ready(second)
        self.assertEqual(sum("clientContent" in event for peer in self.geminis for event in peer.sent), 2)

    async def test_greeting_is_announced_in_hello_before_prompt_send_yields(self):
        self.next_greeting_gate = asyncio.Event()
        first = DevicePeer()
        self.start(first)
        while not self.geminis:
            await asyncio.sleep(0)
        await asyncio.wait_for(self.geminis[0].greeting_started.wait(), 1)
        self.assertIs(first.sent[0].get('greeting_pending'), True)
        self.assertEqual(bridge.DEVICE_CONNECTIONS['device-one'][0], first)

    async def test_each_connection_gets_a_complete_vietnamese_introduction(self):
        first, second = DevicePeer(boot_id=42), DevicePeer(boot_id=42)
        self.start(first)
        await self.ready(first)
        self.start(second)
        await self.ready(second)
        for peer in self.geminis:
            prompts = [event['clientContent']['turns'][0]['parts'][0]['text']
                       for event in peer.sent if 'clientContent' in event]
            self.assertEqual(len(prompts), 1)
            self.assertIn('Chào bé', prompts[0])
            self.assertIn('phát âm', prompts[0])
            self.assertIn('hình ảnh', prompts[0])
            self.assertIn('âm lượng', prompts[0])
            self.assertIn('không nghe rõ', prompts[0])
            self.assertGreater(len(prompts[0].split()), 80)

    async def test_no_intro_audio_resumes_listening_after_bounded_wait(self):
        with patch.object(bridge, 'CONNECTION_GREETING_WAIT_SECONDS', 0.02, create=True):
            device = DevicePeer()
            self.start(device)
            await self.ready(device)
            await asyncio.wait_for(device.wait_sent(
                lambda event: event.get('type') == 'listen' and event.get('state') == 'start'), 0.5)

    async def test_partial_intro_stall_releases_the_owned_connection(self):
        device = DevicePeer()
        stats = {'greeting_pending': True, 'greeting_audio_started': True,
                 'greeting_playout_until': time.monotonic()}
        with patch.object(bridge, 'CONNECTION_GREETING_WAIT_SECONDS', 0.01):
            await asyncio.wait_for(bridge.resume_after_greeting_wait(device, 'session', stats), 0.2)
        self.assertTrue(device.closed.is_set(), 'A partial stalled introduction must release Speaking')
        self.assertEqual(device.close_code, 1011)
        self.assertFalse(stats['greeting_pending'])

    async def test_diagnostic_connection_does_not_reserve_greeting(self):
        with patch.dict(bridge.os.environ, {'WISIO_DIAGNOSTIC': '1'}):
            device = DevicePeer()
            self.start(device)
            await self.ready(device)
        self.assertIs(device.sent[0].get('greeting_pending'), False)
        self.assertFalse(any('clientContent' in event for event in self.geminis[0].sent))

    async def test_silent_completion_does_not_open_microphone_during_intro(self):
        device = DevicePeer()
        with patch.object(bridge, 'CONNECTION_GREETING_WAIT_SECONDS', 0.2):
            self.start(device)
            await self.ready(device)
            self.geminis[0].messages.put_nowait({'serverContent': {'turnComplete': True}})
            device.messages.put_nowait(b'microphone packet')
            await asyncio.sleep(0.03)
            self.assertTrue(self.session_stats[0]['greeting_pending'])
            self.assertEqual(self.session_stats[0]['input_frames'], 0)
            self.assertFalse(any(item.get('type') == 'listen' for item in device.sent))

    async def test_long_intro_keeps_capture_locked_until_audio_completes(self):
        class Playback:
            def __init__(self, *_args, **_kwargs):
                pass
            def put(self, _frame):
                pass
            async def finish(self):
                pass
            async def cancel(self):
                pass
        device = DevicePeer()
        with patch.object(bridge, 'CONNECTION_GREETING_WAIT_SECONDS', 0.05), \
             patch.object(bridge, 'PacedPlayback', Playback):
            self.start(device)
            await self.ready(device)
            self.geminis[0].messages.put_nowait({'serverContent': {'modelTurn': {'parts': [
                {'inlineData': {'data': base64.b64encode(bytes(bridge.OUTPUT_SAMPLES * 2 * 10)).decode('ascii')}}
            ]}}})
            await asyncio.wait_for(device.wait_sent(
                lambda item: item.get('type') == 'tts' and item.get('state') == 'start'), 0.5)
            await asyncio.sleep(0.08)
            device.messages.put_nowait(b'microphone packet')
            await asyncio.sleep(0)
            self.assertTrue(self.session_stats[0]['greeting_pending'])
            self.assertEqual(self.session_stats[0]['input_frames'], 0)
            self.assertFalse(any(item.get('type') == 'listen' for item in device.sent))
            self.geminis[0].messages.put_nowait({'serverContent': {'turnComplete': True}})
            await asyncio.wait_for(device.wait_sent(
                lambda item: item.get('type') == 'tts' and item.get('state') == 'stop'), 0.5)
            # DevicePeer.send yields after publishing the event; let the output
            # handler complete the matching state transition as a real send does.
            await asyncio.sleep(0)
            self.assertFalse(self.session_stats[0]['greeting_pending'])
            device.messages.put_nowait(b'microphone packet')
            await asyncio.sleep(0.01)
            self.assertEqual(self.session_stats[0]['input_frames'], 1)

    async def test_intro_does_not_run_music_or_image_tools(self):
        device = DevicePeer()
        with patch.object(bridge.MusicController, 'prepare', new_callable=AsyncMock) as prepare, \
             patch.object(bridge.learning_prefetch.LearningImagePrefetch, 'schedule') as schedule:
            self.start(device)
            await self.ready(device)
            self.geminis[0].messages.put_nowait({'serverContent': {
                'outputTranscription': {'text': 'Wisio cùng bé học về con mèo và con ong.'}},
                'toolCall': {'functionCalls': [
                    {'id': 'music', 'name': 'play_song', 'args': {'query': 'Song'}},
                    {'id': 'image', 'name': 'show_learning_image', 'args': {'word': 'bee', 'query': 'bee'}},
                ]}})
            await asyncio.wait_for(device.wait_sent(lambda item: item.get('type') == 'tts'), 0.5)
            prepare.assert_not_awaited()
            schedule.assert_not_called()
            responses = [event['toolResponse']['functionResponses'] for event in self.geminis[0].sent
                         if 'toolResponse' in event]
            self.assertEqual(len(responses[0]), 2)
            self.assertTrue(all('error' in item['response'] for item in responses[0]))

    async def test_stalled_old_close_is_bounded_and_aborts_only_old_transport(self):
        first, second = DevicePeer(), DevicePeer()
        self.start(first)
        await self.ready(first)
        aborted = asyncio.Event()
        first.transport = SimpleNamespace(abort=aborted.set)
        first.close_gate = asyncio.Event()
        with patch.object(bridge, "DEVICE_CLEANUP_SECONDS", 0.03):
            new_task = self.start(second)
            await asyncio.wait_for(second.listening.wait(), 0.5)
            await asyncio.wait_for(aborted.wait(), 0.2)
        self.assertFalse(new_task.done())
        self.assertIsNone(second.close_code)
        self.assertEqual(bridge.DEVICE_CONNECTIONS["device-one"][0], second)

    async def test_invalid_uuid_type_cannot_replace_known_device(self):
        first, invalid = DevicePeer(), DevicePeer()
        old_task = self.start(first)
        await self.ready(first)
        invalid.hello["device_uuid"] = {"uuid": "device-one"}
        await asyncio.wait_for(self.start(invalid), 1)
        self.assertFalse(old_task.done())
        self.assertIsNone(first.close_code)
        self.assertEqual(len(self.geminis), 1)

    async def test_rapid_three_reconnects_leave_only_latest_owner(self):
        first, second, third = DevicePeer(), DevicePeer(), DevicePeer()
        first_task = self.start(first)
        await self.ready(first)
        first.close_gate = asyncio.Event()
        second_task = self.start(second)
        async def wait_claim():
            while bridge.DEVICE_CONNECTIONS.get("device-one", (None,))[0] is not second:
                await asyncio.sleep(0)
        await asyncio.wait_for(wait_claim(), 1)
        third_task = self.start(third)
        first.close_gate.set()
        await self.ready(third)
        await asyncio.wait_for(asyncio.gather(first_task, second_task, return_exceptions=True), 2)
        self.assertFalse(third_task.done())
        self.assertEqual(len(bridge.DEVICE_CONNECTIONS), 1)
        self.assertEqual(bridge.DEVICE_CONNECTIONS["device-one"][0], third)
        self.assertEqual(sum(not task.done() for task in self.tasks), 1)

    async def test_failed_prepared_stream_close_still_stops_music_before_codec_destroy(self):
        controllers, codec_users, violations = [], [], []
        original_controller = bridge.MusicController
        def create(*args):
            controller = original_controller(*args)
            controllers.append(controller)
            return controller
        class FailedStream:
            async def aclose(self):
                raise OSError("decoder close failed")
        async def codec_user():
            await asyncio.Event().wait()
        with patch.object(bridge, "MusicController", side_effect=create):
            first, second = DevicePeer(), DevicePeer()
            self.start(first)
            await self.ready(first)
            controller = controllers[0]
            for attribute in ("task", "start_task", "cover_task"):
                task = asyncio.create_task(codec_user())
                codec_users.append(task)
                setattr(controller, attribute, task)
            playback_task = asyncio.create_task(codec_user())
            codec_users.append(playback_task)
            controller.playback = SimpleNamespace(task=playback_task)
            controller.prepared_stream = FailedStream()
            self.codec.before_destroy = lambda: violations.append(True) if any(
                not task.done() for task in codec_users) else None
            try:
                self.start(second)
                await self.ready(second)
                self.assertFalse(violations, "codec was destroyed while an old music worker was alive")
                self.assertTrue(all(task.done() for task in codec_users))
            finally:
                self.codec.before_destroy = lambda: None
                for task in codec_users:
                    task.cancel()
                await asyncio.gather(*codec_users, return_exceptions=True)

    async def test_slow_prepared_stream_close_occurs_after_music_workers_stop(self):
        controller = bridge.MusicController(DevicePeer(), 1, self.codec, "s", 1, {})
        closing = asyncio.Event()
        class SlowStream:
            async def aclose(self):
                closing.set()
                await asyncio.Event().wait()
        async def codec_user():
            await asyncio.Event().wait()
        task = asyncio.create_task(codec_user())
        controller.task = task
        controller.prepared_stream = SlowStream()
        with patch.object(bridge, "DEVICE_CLEANUP_SECONDS", 0.1):
            stop = asyncio.create_task(controller.stop())
            try:
                await asyncio.wait_for(closing.wait(), 0.3)
                self.assertTrue(task.done(), "slow stream close must not keep the codec user alive")
                await asyncio.wait_for(stop, 0.5)
            finally:
                stop.cancel()
                task.cancel()
                await asyncio.gather(stop, task, return_exceptions=True)

    async def test_play_finalizer_stops_playback_and_cover_before_failed_stream_close(self):
        playback_workers = []
        created = asyncio.Event()
        class Playback:
            def __init__(self, *_args, **_kwargs):
                self.queue = asyncio.Queue()
                self.first_packet_sent = asyncio.Event()
                self.task = asyncio.create_task(asyncio.Event().wait())
                playback_workers.append(self.task)
                created.set()
            async def cancel(self):
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
        class Stream:
            async def __anext__(self):
                await asyncio.Event().wait()
            async def aclose(self):
                raise OSError("stream finalizer failed")
        controller = bridge.MusicController(DevicePeer(), 1, self.codec, "s", 1, {})
        controller.prepared_stream = Stream()
        track = SimpleNamespace(title="Song", artist="Artist", duration=0, thumbnail_url="cover")
        cover_workers = []
        async def cover(*_args):
            cover_workers.append(asyncio.current_task())
            await asyncio.Event().wait()
        with patch.object(bridge, "PacedPlayback", Playback), \
             patch.object(controller, "_prepare_cover_art", side_effect=cover):
            play = asyncio.create_task(controller._play(track, "token"))
            try:
                # Artwork can use the bounded 250 ms preparation window first.
                await asyncio.wait_for(created.wait(), 2)
                play.cancel()
                await asyncio.gather(play, return_exceptions=True)
                self.assertTrue(all(task.done() for task in playback_workers),
                                "failed stream close skipped cancellation of speaker codec worker")
                self.assertTrue(all(task.done() for task in cover_workers))
            finally:
                play.cancel()
                for task in [*playback_workers, *cover_workers]:
                    task.cancel()
                await asyncio.gather(play, *playback_workers, *cover_workers, return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
