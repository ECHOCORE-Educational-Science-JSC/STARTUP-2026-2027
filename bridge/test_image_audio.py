"""Image/speech continuity checks with real pacing and no network or hardware."""

import asyncio
import base64
import json
import unittest
from unittest.mock import patch

import bridge


def audio_event(pcm):
    return json.dumps({"serverContent": {"modelTurn": {"parts": [{
        "inlineData": {"data": base64.b64encode(pcm).decode()},
    }]}}})


def image_call(identifier):
    return json.dumps({"toolCall": {"functionCalls": [{
        "id": identifier, "name": "show_learning_image",
        "args": {"word": "cat", "query": "cat"},
    }]}})


def verified_visual():
    return {
        "png": b"verified cached picture", "verified": True,
        "source_title": "Cat", "source_url": "https://example.invalid/cat.png",
    }


class PassThroughCodec:
    def encode(self, encoder, pcm):
        return bytes(pcm)


class InactiveMusic:
    def is_active(self):
        return False

    def is_playing(self):
        return False

    async def defer_for_speech(self):
        pass

    async def schedule_pending(self):
        pass


class PendingImages:
    """A worker result can finish after its shielded foreground wait is cancelled."""
    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.result = asyncio.get_running_loop().create_future()

    def schedule(self, items):
        return len(items)

    async def get(self, query, word, timeout=18):
        self.started.set()
        try:
            return await asyncio.shield(self.result)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise

    async def close(self):
        pass


@unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
class ImageAudioContinuityTest(unittest.IsolatedAsyncioTestCase):
    async def assert_event_occurs(self, event, message):
        try:
            await asyncio.wait_for(event.wait(), 2)
        except TimeoutError:
            self.fail(message)

    async def test_cached_image_preserves_in_progress_pcm_stream(self):
        # Finishing speech at an image call used to pad partial PCM with silence,
        # drain the robot's lead, and settle a second playback before resuming.
        frame_size = bridge.OUTPUT_SAMPLES * 2
        expected_pcm = b"".join(bytes([marker]) * frame_size for marker in range(33))
        split = 16 * frame_size + frame_size // 2
        phase = {"event": "starting"}
        players = []
        finish_phases = []
        device_messages = []
        audio_packets = []
        tool_responses = []

        class Gemini:
            def __aiter__(self):
                async def events():
                    phase["event"] = "speech_prefix"
                    yield json.dumps({"serverContent": {"modelTurn": {"parts": [{
                        "inlineData": {"data": base64.b64encode(expected_pcm[:split]).decode()},
                    }]}}})
                    phase["event"] = "image_tool"
                    yield json.dumps({"toolCall": {"functionCalls": [{
                        "id": "picture", "name": "show_learning_image",
                        "args": {"word": "cat", "query": "cat"},
                    }]}})
                    phase["event"] = "speech_suffix"
                    yield json.dumps({"serverContent": {"modelTurn": {"parts": [{
                        "inlineData": {"data": base64.b64encode(expected_pcm[split:]).decode()},
                    }]}}})
                    phase["event"] = "turn_complete"
                    yield json.dumps({"serverContent": {"turnComplete": True}})
                return events()

            async def send(self, message):
                tool_responses.append(json.loads(message))

        class Device:
            async def send(self, message):
                if isinstance(message, bytes):
                    audio_packets.append(message)
                else:
                    device_messages.append(json.loads(message))

        class Codec:
            def encode(self, encoder, pcm):
                # Preserve the PCM bytes at the Opus boundary so the test can
                # detect padding, loss, or reordering without a native codec.
                return bytes(pcm)

        class Music:
            def is_active(self):
                return False

            def is_playing(self):
                return False

            async def defer_for_speech(self):
                pass

            async def schedule_pending(self):
                pass

        class CachedImages:
            def schedule(self, items):
                return len(items)

            async def get(self, query, word, timeout=18):
                return {
                    "png": b"verified cached picture", "verified": True,
                    "source_title": "Cat", "source_url": "https://example.invalid/cat.png",
                }

            async def close(self):
                pass

        class TrackedPlayback(bridge.PacedPlayback):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                players.append(self)

            async def finish(self):
                finish_phases.append(phase["event"])
                await super().finish()

        stats = {"gemini_content_seen": False, "output_frames": 0}
        with patch.object(bridge.learning_prefetch, "LearningImagePrefetch", return_value=CachedImages()), \
             patch.object(bridge, "PacedPlayback", TrackedPlayback):
            await bridge.gemini_output(
                Gemini(), Device(), None, Codec(), "local-test", 1,
                stats, bridge.new_speech_state(), one_turn=True,
                music_controller=Music(),
            )

        self.assertEqual(len(players), 1, "Drawing an image must keep the current speech playback")
        self.assertEqual(finish_phases, ["turn_complete"], "Only the end of speech may drain playback")
        self.assertEqual(b"".join(audio_packets), expected_pcm, "An image must not pad, drop, or reorder PCM")
        self.assertEqual(stats["output_frames"], 33)
        self.assertEqual([message["word"] for message in device_messages
                          if message.get("type") == "learning_image"], ["cat"])
        self.assertEqual([message["state"] for message in device_messages
                          if message.get("type") == "tts"], ["start", "stop"])
        response = tool_responses[0]["toolResponse"]["functionResponses"][0]
        self.assertEqual(response["id"], "picture")
        self.assertNotIn("error", response["response"])
        self.assertIn("Do not switch an English-only activity to Vietnamese", response["response"]["result"],
                      "A displayed image must preserve an English-only lesson's language")

    async def test_slow_image_does_not_block_gemini_audio_events(self):
        # A blocked image wait must not prevent later Gemini PCM events from
        # being read and delivered through the existing playback scheduler.
        frame_size = bridge.OUTPUT_SAMPLES * 2
        prefix = b"A" * frame_size * 16
        suffix = b"B" * frame_size * 16
        loader = PendingImages()
        suffix_read = asyncio.Event()
        suffix_delivered = asyncio.Event()
        tool_response_sent = asyncio.Event()
        players, audio_packets, messages, responses = [], [], [], []

        class Gemini:
            def __aiter__(self):
                async def events():
                    yield audio_event(prefix)
                    yield image_call("picture-delayed")
                    suffix_read.set()
                    yield audio_event(suffix)
                    yield json.dumps({"serverContent": {"turnComplete": True}})
                    await tool_response_sent.wait()
                return events()

            async def send(self, message):
                value = json.loads(message)
                responses.append(value)
                if value.get("toolResponse"):
                    tool_response_sent.set()

        class Device:
            async def send(self, message):
                if isinstance(message, bytes):
                    audio_packets.append(message)
                    if message == b"B" * frame_size:
                        suffix_delivered.set()
                else:
                    messages.append(json.loads(message))

        class TrackedPlayback(bridge.PacedPlayback):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                players.append(self)

        stats = {"gemini_content_seen": False, "output_frames": 0}
        with patch.object(bridge.learning_prefetch, "LearningImagePrefetch", return_value=loader), \
             patch.object(bridge, "PacedPlayback", TrackedPlayback):
            output = asyncio.create_task(bridge.gemini_output(
                Gemini(), Device(), None, PassThroughCodec(), "local-test", 1,
                stats, bridge.new_speech_state(), one_turn=True,
                music_controller=InactiveMusic(),
            ))
            try:
                await asyncio.wait_for(loader.started.wait(), 3)
                await self.assert_event_occurs(
                    suffix_read, "Image loading blocked the next Gemini audio event")
                await self.assert_event_occurs(
                    suffix_delivered, "Audio after the image call was not delivered while loading waited")
                self.assertFalse(loader.result.done(), "Audio must resume before the image is ready")
                self.assertFalse(any(message.get("type") == "learning_image" for message in messages))
                loader.result.set_result(verified_visual())
                await asyncio.wait_for(output, 5)
            finally:
                if not loader.result.done():
                    loader.result.set_result(verified_visual())
                if not output.done():
                    output.cancel()
                await asyncio.gather(output, return_exceptions=True)

        self.assertEqual(len(players), 1)
        self.assertEqual(b"".join(audio_packets), prefix + suffix)
        self.assertEqual(stats["output_frames"], 32)
        self.assertEqual([message["word"] for message in messages
                          if message.get("type") == "learning_image"], ["cat"])
        function_responses = [reply for response in responses
                              for reply in response.get("toolResponse", {}).get("functionResponses", [])]
        self.assertEqual(len(function_responses), 1)
        self.assertEqual(function_responses[0]["id"], "picture-delayed")
        self.assertNotIn("error", function_responses[0]["response"])

    async def test_tool_call_cancellation_discards_late_image_result(self):
        await self.assert_cancelled_image_does_not_display({
            "toolCallCancellation": {"ids": ["picture-cancel"]},
        })

    async def test_interruption_discards_late_image_result(self):
        await self.assert_cancelled_image_does_not_display({
            "serverContent": {"interrupted": True},
        })

    async def test_tool_cancellation_after_turn_complete_discards_late_image_result(self):
        await self.assert_cancelled_image_does_not_display({
            "toolCallCancellation": {"ids": ["picture-cancel"]},
        }, after_turn_complete=True)

    async def test_interruption_after_turn_complete_discards_late_image_result(self):
        await self.assert_cancelled_image_does_not_display({
            "serverContent": {"interrupted": True},
        }, after_turn_complete=True)

    async def test_new_input_after_turn_complete_discards_previous_image_result(self):
        await self.assert_cancelled_image_does_not_display({
            "serverContent": {"inputTranscription": {"text": "Show me a dog"}},
        }, after_turn_complete=True, initial_input="Show me a cat")

    async def assert_cancelled_image_does_not_display(self, cancellation, after_turn_complete=False,
                                                     initial_input=None):
        loader = PendingImages()
        cancellation_read = asyncio.Event()
        late_result_released = asyncio.Event()
        messages, responses = [], []

        class Gemini:
            def __aiter__(self):
                async def events():
                    if initial_input is not None:
                        yield json.dumps({"serverContent": {
                            "inputTranscription": {"text": initial_input},
                        }})
                    yield image_call("picture-cancel")
                    await loader.started.wait()
                    if after_turn_complete:
                        yield json.dumps({"serverContent": {"turnComplete": True}})
                    yield json.dumps(cancellation)
                    cancellation_read.set()
                    # Keep the connection open until the uncancellable worker
                    # finishes, so connection teardown cannot hide a stale send.
                    await late_result_released.wait()
                    yield json.dumps({"serverContent": {"turnComplete": True}})
                return events()

            async def send(self, message):
                responses.append(json.loads(message))

        class Device:
            async def send(self, message):
                messages.append(json.loads(message))

        with patch.object(bridge.learning_prefetch, "LearningImagePrefetch", return_value=loader):
            output = asyncio.create_task(bridge.gemini_output(
                Gemini(), Device(), None, None, "local-test", 1,
                {"gemini_content_seen": False, "output_frames": 0},
                bridge.new_speech_state(), one_turn=True,
                music_controller=InactiveMusic(),
            ))
            try:
                await asyncio.wait_for(loader.started.wait(), 2)
                await self.assert_event_occurs(
                    cancellation_read, "Image loading blocked the Gemini cancellation event")
                await self.assert_event_occurs(
                    loader.cancelled, "Cancellation left the old image request active")
                # Cancellation must end the foreground wait, while the shared
                # worker result remains available for a later valid request.
                self.assertFalse(loader.result.done())
                loader.result.set_result(verified_visual())
                late_result_released.set()
                await asyncio.wait_for(output, 3)
            finally:
                if not loader.result.done():
                    loader.result.set_result(verified_visual())
                late_result_released.set()
                if not output.done():
                    output.cancel()
                await asyncio.gather(output, return_exceptions=True)

        self.assertFalse(any(message.get("type") == "learning_image" for message in messages),
                         "A cancelled request must never display its late image")
        successes = [reply for response in responses
                     for reply in response.get("toolResponse", {}).get("functionResponses", [])
                     if reply.get("id") == "picture-cancel" and "error" not in reply.get("response", {})]
        self.assertEqual(successes, [], "A cancelled request must not claim an image appeared")


if __name__ == "__main__":
    unittest.main()
