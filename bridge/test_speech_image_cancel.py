"""Physical speech must invalidate old images before Gemini transcribes it."""

import asyncio
from contextlib import asynccontextmanager, redirect_stdout
import io
import json
import struct
import unittest
from unittest.mock import patch

import bridge
from test_image_audio import image_call, verified_visual


class PendingImages:
    """Keep the worker's eventual outcome separate from its cancellable wait."""
    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.result = asyncio.get_running_loop().create_future()

    def schedule(self, items):
        return len(items)

    async def get(self, query, word, timeout=18):
        self.started.set()
        try:
            result = await asyncio.shield(self.result)
            if isinstance(result, Exception):
                raise result
            return result
        except asyncio.CancelledError:
            self.cancelled.set()
            raise

    async def close(self):
        pass


@unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
class SpeechImageCancellationTest(unittest.IsolatedAsyncioTestCase):
    async def test_new_physical_speech_discards_late_image_success(self):
        await self.run_device_case(new_speech=True, failure=False)

    async def test_new_physical_speech_discards_late_image_failure(self):
        await self.run_device_case(new_speech=True, failure=True)

    async def test_quiet_listen_start_keeps_pending_image(self):
        await self.run_device_case(new_speech=False, failure=False)

    async def test_new_speech_discards_late_fallback_image_success(self):
        await self.run_device_case(new_speech=True, failure=False, fallback=True)

    async def test_new_speech_discards_late_fallback_image_failure(self):
        await self.run_device_case(new_speech=True, failure=True, fallback=True)

    async def test_queued_old_interruption_keeps_new_microphone_stream_open(self):
        await self.run_device_case(new_speech=True, failure=False, trailing_server_event="interrupted")

    async def run_device_case(self, new_speech, failure, fallback=False,
                              trailing_server_event="turnComplete"):
        loader = PendingImages()
        mic_received = asyncio.Event()
        quiet_listen_processed = asyncio.Event()
        image_delivered = asyncio.Event()
        queued_server_event_processed = asyncio.Event()
        additional_frame_processed = asyncio.Event()
        device_input, gemini_input = asyncio.Queue(), asyncio.Queue()
        device_messages, gemini_messages = [], []
        pending_forever = asyncio.Event()

        class Gemini:
            async def recv(self):
                return json.dumps({"setupComplete": {}})

            def __aiter__(self):
                async def events():
                    while True:
                        event = await gemini_input.get()
                        yield event
                        if json.loads(event).get("test_marker"):
                            queued_server_event_processed.set()
                return events()

            async def send(self, raw):
                event = json.loads(raw)
                gemini_messages.append(event)
                if "audio" in event.get("realtimeInput", {}):
                    mic_received.set()

        gemini = Gemini()

        @asynccontextmanager
        async def connected(_key):
            yield gemini

        class Device:
            request = type("Request", (), {"path": "/wisio/v1/"})()
            close_code = None

            async def recv(self):
                return json.dumps({"type": "hello", "transport": "websocket",
                                   "version": 1, "wisio_id": "unknown"})

            def __aiter__(self):
                async def events():
                    while True:
                        raw = await device_input.get()
                        if raw is None:
                            return
                        yield raw
                        if isinstance(raw, str) and json.loads(raw).get("type") == "listen":
                            quiet_listen_processed.set()
                        if isinstance(raw, str) and json.loads(raw).get("type") == "test_barrier":
                            additional_frame_processed.set()
                return events()

            async def send(self, raw):
                if isinstance(raw, str):
                    event = json.loads(raw)
                    device_messages.append(event)
                    if event.get("type") == "learning_image":
                        image_delivered.set()

            async def close(self, code=1000, reason=""):
                self.close_code = code

        class Codec:
            lib = type("Library", (), {
                "opus_decoder_destroy": staticmethod(lambda decoder: None),
                "opus_encoder_destroy": staticmethod(lambda encoder: None),
            })()

            def decoder(self, rate):
                return None

            def encoder(self, rate, application):
                return None

            def decode(self, decoder, packet):
                return packet

        class Memory:
            def prompt_context(self):
                return ""

        async def watch(*args):
            await pending_forever.wait()

        await gemini_input.put(json.dumps({"serverContent": {
            "inputTranscription": {"text": "Show me a cat"}}}))
        if fallback:
            await gemini_input.put(json.dumps({"serverContent": {"turnComplete": True}}))
        else:
            await gemini_input.put(image_call("old-picture"))
        await gemini_input.put(json.dumps({"serverContent": {"turnComplete": True}}))
        captured = io.StringIO()
        with patch.object(bridge, "connect_gemini", connected), \
             patch.object(bridge, "PersistentMemory", Memory), \
             patch.object(bridge, "watch_gemini", watch), \
             patch.object(bridge.learning_prefetch, "LearningImagePrefetch", return_value=loader), \
             redirect_stdout(captured):
            handler = asyncio.create_task(bridge.handle_device(Device(), "unused-test-key", Codec()))
            try:
                await asyncio.wait_for(loader.started.wait(), 2)
                await device_input.put(json.dumps({"type": "listen", "state": "start", "mode": "auto"}))
                await asyncio.wait_for(quiet_listen_processed.wait(), 2)
                self.assertFalse(loader.cancelled.is_set(),
                                 "Quiet listening must not cancel a valid proactive illustration")
                if new_speech:
                    # Calibrate room silence before two real onset frames. No transcription
                    # for this speech is ever sent by the Gemini fixture.
                    for _ in range(5):
                        await device_input.put(bytes(1920))
                    pcm = struct.pack("<h", 2000) * 960
                    await device_input.put(pcm)
                    await device_input.put(pcm)
                    await asyncio.wait_for(mic_received.wait(), 2)
                    try:
                        await asyncio.wait_for(loader.cancelled.wait(), 0.3)
                    except TimeoutError:
                        self.fail("Physical speech left the old image active until a future transcription")
                if failure:
                    loader.result.set_result(bridge.learning_image.LearningImageError("old network timeout"))
                else:
                    loader.result.set_result(verified_visual())
                if new_speech:
                    # Let a late worker completion and queued server event run
                    # before device teardown, so cleanup cannot hide stale output.
                    await gemini_input.put(json.dumps({"serverContent": {
                        trailing_server_event: True}, "test_marker": True}))
                    await asyncio.wait_for(queued_server_event_processed.wait(), 2)
                    await device_input.put(pcm)
                    await device_input.put(json.dumps({"type": "test_barrier"}))
                    await asyncio.wait_for(additional_frame_processed.wait(), 2)
                    self.assertFalse(image_delivered.is_set())
                    self.assertFalse(any(reply.get("id") == "old-picture"
                                         for event in gemini_messages
                                         for reply in event.get("toolResponse", {}).get("functionResponses", [])),
                                     "An obsolete image must send neither success nor error to Gemini")
                    self.assertNotIn("[TOOL ERROR]", captured.getvalue())
                    self.assertNotIn("[IMAGE FALLBACK ERROR]", captured.getvalue())
                    input_frames = [event for event in gemini_messages
                                    if "audio" in event.get("realtimeInput", {})]
                    self.assertEqual(len(input_frames), 8,
                                     "An old model event must not reset the user's new microphone stream")
                else:
                    await asyncio.wait_for(image_delivered.wait(), 2)
            finally:
                if not loader.result.done():
                    loader.result.set_result(verified_visual())
                await device_input.put(None)
                try:
                    await asyncio.wait_for(handler, 2)
                finally:
                    if not handler.done():
                        handler.cancel()
                    await asyncio.gather(handler, return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
