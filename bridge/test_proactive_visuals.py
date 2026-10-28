"""Automatic illustrations follow the concrete topic without extra model turns."""
import asyncio
import base64
import json
import unittest
from unittest.mock import patch

import bridge
from learning_session import LearningVisualState
from test_image_audio import InactiveMusic, PassThroughCodec, verified_visual


class ProactiveTopicTest(unittest.TestCase):
    def test_meal_suggestion_uses_the_actual_dish_in_the_answer(self):
        state = LearningVisualState()
        state.observe_user('Hôm nay ăn món gì ngon nhỉ?')
        state.observe_assistant('Bé có thể thử bún bò Huế, món bún nước đậm đà.')
        self.assertEqual(state.turn_word, 'bun bo hue')
        self.assertTrue(state.visual_required)

    def test_story_topic_preserves_the_assistant_scene(self):
        state = LearningVisualState()
        state.observe_user('Kể một câu chuyện thú vị nhé')
        state.observe_assistant('Ngày xưa có một con mèo màu cam đang ngủ trên ghế.')
        word, query = state.automatic_request()
        self.assertEqual(word, 'cat')
        self.assertIn('orange', query)
        self.assertIn('sleeping', query)

    def test_music_clarification_and_abstract_talk_never_guess_images(self):
        for user, answer in (
                ('Phát nhạc con mèo', 'Con mèo là một bài hát.'),
                ('Kể chuyện nhé', 'Wisio chưa nghe rõ. Bé nhắc lại về con mèo được không?'),
                ('Xin chào', 'Chào bé! Wisio luôn bên bé.'),
                ('Hôm nay tôi buồn', 'Bé hãy hít thở chậm và nghỉ một chút.')):
            with self.subTest(user=user):
                state = LearningVisualState()
                state.observe_user(user)
                state.observe_assistant(answer)
                self.assertIsNone(state.automatic_request())


@unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
class AutomaticImageFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_text_only_automatic_visual_reopens_listening(self):
        messages = []

        class Gemini:
            def __aiter__(self):
                async def events():
                    yield json.dumps({'serverContent': {
                        'inputTranscription': {'text': 'Kể một câu chuyện thú vị nhé'},
                        'outputTranscription': {'text': 'Ngày xưa có một con mèo màu cam.'},
                        'turnComplete': True}})
                return events()

            async def send(self, message):
                pass

        class Device:
            async def send(self, message):
                messages.append(json.loads(message))

        class Loader:
            def schedule(self, items):
                return len(items)

            async def get(self, query, word, timeout=18):
                return verified_visual()

            async def close(self):
                pass

        with patch.object(bridge.learning_prefetch, 'LearningImagePrefetch', return_value=Loader()):
            await bridge.gemini_output(Gemini(), Device(), None, None, 's', 1,
                                      {'gemini_content_seen': False}, bridge.new_speech_state(),
                                      music_controller=InactiveMusic())
        self.assertTrue(any(item.get('type') == 'listen' and item.get('state') == 'start'
                            for item in messages))

    async def test_new_voice_cancels_pending_automatic_display(self):
        started, release = asyncio.Event(), asyncio.Event()
        events = asyncio.Queue()
        messages, replies, stats = [], [], {'gemini_content_seen': False}

        class Gemini:
            def __aiter__(self):
                async def receive():
                    while (raw := await events.get()) is not None:
                        yield raw
                return receive()

            async def send(self, message):
                replies.append(json.loads(message))

        class Device:
            async def send(self, message):
                messages.append(json.loads(message))

        class Loader:
            def schedule(self, items):
                return len(items)

            async def get(self, query, word, timeout=18):
                started.set()
                await release.wait()
                return verified_visual()

            async def close(self):
                pass

        with patch.object(bridge.learning_prefetch, 'LearningImagePrefetch', return_value=Loader()):
            output = asyncio.create_task(bridge.gemini_output(
                Gemini(), Device(), None, None, 's', 1, stats, bridge.new_speech_state(),
                music_controller=InactiveMusic()))
            try:
                events.put_nowait(json.dumps({'serverContent': {
                    'inputTranscription': {'text': 'Kể một câu chuyện thú vị nhé'},
                    'outputTranscription': {'text': 'Ngày xưa có một con mèo màu cam.'},
                    'turnComplete': True}}))
                await asyncio.wait_for(started.wait(), 1)
                stats['cancel_previous_visual_on_speech']()
                release.set()
                events.put_nowait(None)
                await asyncio.wait_for(output, 1)
            finally:
                release.set()
                output.cancel()
                await asyncio.gather(output, return_exceptions=True)
        self.assertFalse(any(item.get('type') == 'learning_image' for item in messages))
        self.assertEqual(replies, [])

    async def test_skipped_tool_displays_ready_picture_before_explanation_audio(self):
        messages, requests, responses, audio_packets = [], [], [], []
        queued = asyncio.Event()
        frame_size = bridge.OUTPUT_SAMPLES * 2
        pcm = b'A' * frame_size * 16

        class Loader:
            def schedule(self, items):
                requests.extend(items)
                if items:
                    queued.set()
                return len(items)

            async def get(self, query, word, timeout=18):
                return verified_visual()

            async def close(self):
                pass

        class Gemini:
            def __aiter__(self):
                async def events():
                    yield json.dumps({'serverContent': {'inputTranscription': {'text': 'Kể một câu chuyện thú vị nhé'}}})
                    yield json.dumps({'serverContent': {
                        'outputTranscription': {'text': 'Ngày xưa có một con mèo màu cam đang ngủ trên ghế.'},
                        'modelTurn': {'parts': [{'inlineData': {'data': base64.b64encode(pcm).decode()}}]}}})
                    await asyncio.wait_for(queued.wait(), 1)
                    yield json.dumps({'serverContent': {'turnComplete': True}})
                return events()

            async def send(self, message):
                responses.append(json.loads(message))

        class Device:
            async def send(self, message):
                if isinstance(message, str):
                    messages.append(json.loads(message))
                else:
                    audio_packets.append(message)

        with patch.object(bridge.learning_prefetch, 'LearningImagePrefetch', return_value=Loader()):
            await bridge.gemini_output(Gemini(), Device(), None, PassThroughCodec(), 's', 1,
                                      {'gemini_content_seen': False, 'output_frames': 0},
                                      bridge.new_speech_state(), one_turn=True,
                                      music_controller=InactiveMusic())
        pictures = [i for i, item in enumerate(messages) if item.get('type') == 'learning_image']
        starts = [i for i, item in enumerate(messages) if item.get('type') == 'tts' and item.get('state') == 'start']
        self.assertEqual(len(pictures), 1)
        self.assertLess(pictures[0], starts[0], 'Show the ready illustration before explaining it aloud')
        self.assertEqual(requests[-1]['word'], 'cat')
        self.assertEqual(b''.join(audio_packets), pcm, 'Preparing a topic must preserve every audio frame')
        self.assertFalse(any('clientContent' in response for response in responses),
                         'Do not add a correction speech turn just to get a skipped illustration')
