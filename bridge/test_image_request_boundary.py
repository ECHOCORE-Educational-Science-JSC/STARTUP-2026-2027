"""Exercise request boundaries and dish identity without network or robot hardware."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import bridge
from test_image_audio import InactiveMusic, verified_visual


class ImageRequestBoundaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_new_transcript_in_tool_event_replaces_previous_subject_first(self):
        state = bridge.learning_session.LearningVisualState()
        state.observe_user('Show me an elephant')
        stats = {'gemini_content_seen': False, 'input_turns': 1}
        loader = MagicMock(get=AsyncMock(return_value=verified_visual()),
                           close=AsyncMock())
        responded = asyncio.Event()
        replies = []

        class Gemini:
            def __aiter__(self):
                async def events():
                    stats['input_turns'] += 1
                    yield json.dumps({
                        'serverContent': {'inputTranscription': {'text': 'chân gà được không'}},
                        'toolCall': {'functionCalls': [{
                            'id': 'feet', 'name': 'show_learning_image',
                            'args': {'word': 'chicken', 'query': 'chicken feet dish'},
                        }]},
                    })
                    await asyncio.wait_for(responded.wait(), 2)
                return events()

            async def send(self, message):
                event = json.loads(message)
                if event.get('toolResponse'):
                    replies.extend(event['toolResponse']['functionResponses'])
                    responded.set()

        device = MagicMock(send=AsyncMock())
        with patch.object(bridge.learning_prefetch, 'LearningImagePrefetch', return_value=loader):
            await bridge.gemini_output(Gemini(), device, None, None, 's', 1,
                                      stats, bridge.new_speech_state(),
                                      music_controller=InactiveMusic(), learning_visual_state=state)
        self.assertNotIn('error', replies[0]['response'])
        self.assertEqual(loader.get.await_count, 1)
        self.assertEqual(loader.get.call_args.args[1], 'chan ga')
        self.assertNotIn('elephant', loader.get.call_args.args[0])

    def test_dish_translation_is_accepted_inside_real_vocabulary_list(self):
        state = bridge.learning_session.LearningVisualState()
        state.observe_user('Dạy các từ elephant và chân gà')
        word, query = state.authoritative_visual_request('chicken feet', 'chicken feet dish')
        self.assertEqual(word, 'chan ga')
        self.assertNotIn('elephant', query)
        word, query = state.authoritative_visual_request('chicken', 'chicken feet dish')
        self.assertEqual(word, 'chan ga')
        with self.assertRaises(bridge.learning_image.LearningImageError):
            state.authoritative_visual_request('chicken', 'one chicken')

    async def test_network_failure_is_not_retried_by_continuation_or_fallback(self):
        state = bridge.learning_session.LearningVisualState()
        loader = MagicMock(get=AsyncMock(side_effect=bridge.learning_image.LearningImageError(
            'SERPAPI_TIMEOUT_OR_NETWORK')), close=AsyncMock())
        replied = asyncio.Event()
        responses = []

        class Gemini:
            def __aiter__(self):
                async def events():
                    yield json.dumps({'serverContent': {'inputTranscription': {
                        'text': 'Cho xem chân gà'}}})
                    for ident in ('first', 'repeat'):
                        replied.clear()
                        yield json.dumps({'toolCall': {'functionCalls': [{
                            'id': ident, 'name': 'show_learning_image',
                            'args': {'word': 'chicken', 'query': 'chicken feet'},
                        }]}})
                        await asyncio.wait_for(replied.wait(), 2)
                        yield json.dumps({'serverContent': {'turnComplete': True}})
                return events()

            async def send(self, message):
                event = json.loads(message)
                responses.append(event)
                if event.get('toolResponse'):
                    replied.set()

        with patch.object(bridge.learning_prefetch, 'LearningImagePrefetch', return_value=loader):
            await bridge.gemini_output(Gemini(), MagicMock(send=AsyncMock()), None, None, 's', 1,
                                      {'gemini_content_seen': False}, bridge.new_speech_state(),
                                      music_controller=InactiveMusic(), learning_visual_state=state)
        self.assertEqual(loader.get.await_count, 1)
        self.assertFalse(any(event.get('clientContent') for event in responses))
