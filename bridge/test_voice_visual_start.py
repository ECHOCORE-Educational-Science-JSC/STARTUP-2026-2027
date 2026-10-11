"""Preparation overlaps model response; screen updates never split spoken PCM."""
import asyncio
import base64
import json
import unittest
from unittest.mock import patch

import bridge
from learning_session import LearningVisualState
from test_image_audio import InactiveMusic, PassThroughCodec, verified_visual


class EarlyTopicTest(unittest.TestCase):
    def test_38_live_can_acknowledge_image_search_while_music_stays_sequential(self):
        tools = bridge.live_tools_for_model('gemini-3.8-live')
        declarations = {d['name']: d for d in tools[0]['functionDeclarations']}
        self.assertEqual(declarations['show_learning_image']['behavior'], 'NON_BLOCKING')
        self.assertNotIn('behavior', declarations['play_song'])
        older = bridge.live_tools_for_model('gemini-3.1-flash-live-preview')
        self.assertFalse(any('behavior' in d for d in older[0]['functionDeclarations']))

    def test_single_drink_is_prefetched_before_any_assistant_reply(self):
        state = LearningVisualState()
        state.observe_user('Vậy còn trà tắc thì sao?')
        self.assertEqual(state.prefetch_requests(), [{'word': 'tra tac', 'query': 'tra tac photo'}])
        self.assertEqual(state.prefetch_requests(), [])

    def test_serving_refinement_preserves_attributes_and_gets_its_own_job(self):
        state = LearningVisualState()
        state.observe_user('Cho xem trà tắc')
        first = state.prefetch_requests()
        state.observe_user('trong hai ly thủy tinh có đá')
        refined = state.prefetch_requests()
        self.assertEqual(refined[0]['word'], 'tra tac')
        self.assertNotEqual(first[0]['query'], refined[0]['query'])
        self.assertIn('hai ly thuy tinh co da', refined[0]['query'])


class VisualSpeechStartTest(unittest.IsolatedAsyncioTestCase):
    async def run_explicit_mid_voice(self, abrupt=False):
        trace, replies = [], []
        release = asyncio.Event()
        pcm = b'S' * bridge.OUTPUT_SAMPLES * 2 * 4

        class Loader:
            def schedule(self, items): return len(items)
            async def get(self, query, word, timeout=30):
                await release.wait()
                return verified_visual()
            async def close(self): pass

        class Device:
            async def send(self, message):
                trace.append(json.loads(message) if isinstance(message, str) else message)

        owner = self
        class Gemini:
            def __aiter__(self):
                async def events():
                    yield json.dumps({'serverContent': {'inputTranscription': {'text': 'Cho xem con mèo'}}})
                    yield json.dumps({'toolCall': {'functionCalls': [{
                        'id': 'image', 'name': 'show_learning_image',
                        'args': {'word': 'cat', 'query': 'cat photo'}}]}})
                    yield json.dumps({'serverContent': {'modelTurn': {'parts': [{
                        'inlineData': {'data': base64.b64encode(pcm).decode()}}]}}})
                    release.set()
                    await asyncio.sleep(.02)
                    owner.assertFalse(any(isinstance(x, dict) and x.get('type') == 'learning_image'
                                          for x in trace))
                    if not abrupt:
                        yield json.dumps({'serverContent': {'turnComplete': True}})
                return events()
            async def send(self, message): replies.append(json.loads(message))

        with patch.object(bridge.learning_prefetch, 'LearningImagePrefetch', return_value=Loader()), \
             patch.object(bridge, 'VISUAL_SPEECH_WAIT_SECONDS', .001):
            await bridge.gemini_output(Gemini(), Device(), None, PassThroughCodec(), 's', 1,
                                      {'gemini_content_seen': False, 'output_frames': 0},
                                      bridge.new_speech_state(), one_turn=True,
                                      music_controller=InactiveMusic())
        if abrupt:
            self.assertFalse(any(isinstance(x, dict) and x.get('type') == 'learning_image'
                                 for x in trace))
            self.assertFalse(any('toolResponse' in x for x in replies))
            return
        self.assertEqual(b''.join(x for x in trace if isinstance(x, bytes)), pcm)
        picture = next(i for i, x in enumerate(trace) if isinstance(x, dict) and x.get('type') == 'learning_image')
        stop = next(i for i, x in enumerate(trace) if isinstance(x, dict) and x.get('type') == 'tts' and x.get('state') == 'stop')
        self.assertGreater(picture, stop)
        result = replies[-1]['toolResponse']['functionResponses'][0]['response']
        self.assertEqual(result['scheduling'], 'WHEN_IDLE')

    async def test_explicit_image_ready_mid_voice_waits_for_pcm_drain_without_interrupting(self):
        await self.run_explicit_mid_voice()

    async def test_remote_eof_cancels_image_waiting_for_speech_boundary(self):
        await asyncio.wait_for(self.run_explicit_mid_voice(abrupt=True), 2)

    async def run_reply(self, slow=False, failure=False, unexpected_failure=False):
        trace, requests, responses = [], [], []
        release = asyncio.Event()
        pcm = b'Q' * bridge.OUTPUT_SAMPLES * 2 * 8

        class Loader:
            def schedule(self, items):
                requests.extend(items)
                return len(items)

            async def get(self, query, word, timeout=18):
                if slow:
                    await release.wait()
                if failure:
                    raise bridge.learning_image.LearningImageError('GOOGLE_NO_VERIFIED_MATCH')
                if unexpected_failure:
                    raise OSError('temporary cache read failure')
                return verified_visual()

            async def close(self):
                pass

        class Device:
            async def send(self, message):
                trace.append(json.loads(message) if isinstance(message, str) else message)

        class Gemini:
            def __aiter__(self):
                async def events():
                    yield json.dumps({'serverContent': {'inputTranscription': {'text': 'Vậy còn trà tắc thì sao?'}}})
                    self_test.assertEqual(requests[0]['word'], 'tra tac')
                    self_test.assertEqual(requests[0]['query'], 'tra tac photo')
                    yield json.dumps({'serverContent': {
                        'outputTranscription': {'text': 'Trà tắc là trà pha với quả tắc.'},
                        'modelTurn': {'parts': [{'inlineData': {'data': base64.b64encode(pcm).decode()}}]}}})
                    release.set()
                    yield json.dumps({'serverContent': {'turnComplete': True}})
                return events()

            async def send(self, message):
                responses.append(json.loads(message))

        self_test = self
        with patch.object(bridge.learning_prefetch, 'LearningImagePrefetch', return_value=Loader()), \
             patch.object(bridge, 'VISUAL_SPEECH_WAIT_SECONDS', .02, create=True):
            await bridge.gemini_output(Gemini(), Device(), None, PassThroughCodec(), 's', 1,
                                      {'gemini_content_seen': False, 'output_frames': 0},
                                      bridge.new_speech_state(), one_turn=True,
                                      music_controller=InactiveMusic())
        self.assertEqual(b''.join(x for x in trace if isinstance(x, bytes)), pcm)
        self.assertFalse(any('clientContent' in x for x in responses))
        return trace

    async def test_ready_drink_arrives_before_first_voice_packet(self):
        trace = await self.run_reply()
        picture = next(i for i, x in enumerate(trace) if isinstance(x, dict) and x.get('type') == 'learning_image')
        start = next(i for i, x in enumerate(trace) if isinstance(x, dict) and x.get('type') == 'tts' and x.get('state') == 'start')
        voice = next(i for i, x in enumerate(trace) if isinstance(x, bytes))
        self.assertLess(picture, start)
        self.assertLess(start, voice)

    async def test_slow_provider_does_not_stall_voice_or_decode_picture_mid_sentence(self):
        trace = await asyncio.wait_for(self.run_reply(slow=True), 2)
        picture = next(i for i, x in enumerate(trace) if isinstance(x, dict) and x.get('type') == 'learning_image')
        stop = next(i for i, x in enumerate(trace) if isinstance(x, dict) and x.get('type') == 'tts' and x.get('state') == 'stop')
        self.assertGreater(picture, stop)

    async def test_failed_automatic_picture_does_not_add_a_second_spoken_turn(self):
        trace = await self.run_reply(failure=True)
        self.assertFalse(any(isinstance(x, dict) and x.get('type') == 'learning_image' for x in trace))

    async def test_preparation_io_failure_keeps_the_voice_connection_alive(self):
        trace = await self.run_reply(unexpected_failure=True)
        self.assertFalse(any(isinstance(x, dict) and x.get('type') == 'learning_image' for x in trace))

    async def test_new_utterance_cancels_the_picture_and_pcm_waiting_at_first_audio(self):
        stats = {'gemini_content_seen': False, 'output_frames': 0}
        trace, calls = [], []
        pcm = b'R' * bridge.OUTPUT_SAMPLES * 2 * 4

        class Loader:
            def schedule(self, items):
                return len(items)

            async def get(self, query, word, timeout=18):
                calls.append(word)
                if word == 'tra tac':
                    stats['cancel_previous_visual_on_speech']()
                    await asyncio.sleep(0)
                return verified_visual()

            async def close(self):
                pass

        class Device:
            async def send(self, message):
                trace.append(json.loads(message) if isinstance(message, str) else message)

        class Gemini:
            def __aiter__(self):
                async def events():
                    for question in ('Vậy còn trà tắc thì sao?', 'Cho xem con mèo'):
                        yield json.dumps({'serverContent': {
                            'inputTranscription': {'text': question},
                            'modelTurn': {'parts': [{'inlineData': {'data': base64.b64encode(pcm).decode()}}]}}})
                        yield json.dumps({'serverContent': {'turnComplete': True}})
                return events()

            async def send(self, message):
                pass

        with patch.object(bridge.learning_prefetch, 'LearningImagePrefetch', return_value=Loader()):
            await bridge.gemini_output(Gemini(), Device(), None, PassThroughCodec(), 's', 1,
                                      stats, bridge.new_speech_state(), one_turn=True,
                                      music_controller=InactiveMusic())
        self.assertEqual(calls, ['tra tac', 'cat'])
        self.assertEqual(b''.join(x for x in trace if isinstance(x, bytes)), pcm)
        pictures = [x for x in trace if isinstance(x, dict) and x.get('type') == 'learning_image']
        self.assertEqual([x['word'] for x in pictures], ['cat'])


if __name__ == '__main__':
    unittest.main()
