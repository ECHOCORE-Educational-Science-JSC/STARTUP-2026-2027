"""Unclear speech must pause actions until the listener supplies real input."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import bridge


def tool(ident, name, **args):
    return {'toolCall': {'functionCalls': [{'id': ident, 'name': name, 'args': args}]}}


class HearingClarificationTest(unittest.IsolatedAsyncioTestCase):
    async def run_events(self, events, state=None):
        replies, packets = [], []

        class Gemini:
            def __aiter__(self):
                async def source():
                    for event in events:
                        yield json.dumps(event)
                return source()

            async def send(self, data):
                replies.append(json.loads(data))

        class Device:
            async def send(self, data):
                packets.append(json.loads(data))

        controller = MagicMock()
        controller.is_active.return_value = False
        controller.is_playing.return_value = False
        controller.prepare = AsyncMock()
        controller.schedule_pending = AsyncMock()
        controller.stop = AsyncMock()
        memory = MagicMock()
        loader = MagicMock()
        loader.get = AsyncMock(return_value={'png': b'checked cat', 'verified': True})
        loader.close = AsyncMock()
        with patch.object(bridge.learning_prefetch, 'LearningImagePrefetch', return_value=loader):
            await bridge.gemini_output(
                Gemini(), Device(), None, None, 's', 1,
                {'gemini_content_seen': False}, bridge.new_speech_state(),
                music_controller=controller, memory_store=memory, learning_visual_state=state)
        responses = {item['id']: item['response'] for event in replies
                     for item in event.get('toolResponse', {}).get('functionResponses', [])}
        return responses, packets, controller, memory, loader, replies

    async def test_unclear_hearing_blocks_actions_and_automatic_visuals(self):
        state = bridge.learning_session.LearningVisualState()
        state.observe_user('Dạy cat và dog')
        events = [
            tool('clarify', 'request_clarification', question='Bé muốn xem con gì nhỉ?'),
            tool('image', 'show_learning_image', word='cat', query='cat'),
            tool('batch', 'prefetch_learning_images', items=[{'word': 'cat', 'query': 'cat'}]),
            tool('music', 'play_song', query='Baby Shark'),
            tool('volume', 'adjust_volume', action='up'),
            tool('memory', 'remember_user_fact', fact='Bé thích mèo'),
            tool('progress', 'remember_learning_progress', learner='Bo', skill='grammar', topic='be',
                 level='A1', evidence='Guessed speech', next_step='be', status='practising'),
            tool('recall', 'recall_user_memories', learner='Bo', query='be'),
            {'serverContent': {'turnComplete': True}},
        ]
        responses, packets, music, memory, loader, replies = await self.run_events(events, state)
        self.assertEqual(responses['clarify']['question'], 'Bé muốn xem con gì nhỉ?')
        for ident in ('image', 'batch', 'music', 'volume', 'memory', 'progress', 'recall'):
            self.assertIn('error', responses[ident])
        self.assertFalse(any(item.get('type') in ('learning_image', 'volume') for item in packets))
        music.prepare.assert_not_awaited()
        memory.remember.assert_not_called()
        memory.remember_learning_progress.assert_not_called()
        memory.recall.assert_not_called()
        loader.get.assert_not_awaited()
        self.assertFalse(any('clientContent' in reply for reply in replies))
        self.assertTrue(state.waiting_for_clarification)

    async def test_new_input_unlocks_requested_volume_only(self):
        events = [
            tool('clarify', 'request_clarification', question='Wisio chưa nghe rõ, bé nhắc lại nhé?'),
            {'serverContent': {'turnComplete': True}},
            {'serverContent': {'inputTranscription': {'text': 'Tăng âm lượng giúp tôi'}}},
            tool('volume', 'adjust_volume', action='up'),
            {'serverContent': {'turnComplete': True}},
        ]
        responses, packets, music, memory, loader, replies = await self.run_events(events)
        self.assertNotIn('error', responses['volume'])
        self.assertEqual([item['action'] for item in packets if item.get('type') == 'volume'], ['up'])
        loader.get.assert_not_awaited()

    async def test_spoken_clarification_also_blocks_late_guessed_tool(self):
        events = [
            {'serverContent': {'inputTranscription': {'text': 'Con mèo hay cái gì đó'}}},
            {'serverContent': {'outputTranscription': {'text': 'Wisio chưa nghe rõ, bé nhắc lại nhé?'}}},
            tool('guess', 'show_learning_image', word='cat', query='cat'),
            {'serverContent': {'turnComplete': True}},
        ]
        responses, packets, music, memory, loader, replies = await self.run_events(events)
        self.assertIn('error', responses['guess'])
        loader.get.assert_not_awaited()
        self.assertFalse(any(item.get('type') == 'learning_image' for item in packets))
        self.assertFalse(any('clientContent' in reply for reply in replies))

    async def test_idle_remains_quiet_while_waiting_for_clarification(self):
        state = bridge.learning_session.LearningVisualState()
        state.request_clarification()
        gemini = MagicMock(send=AsyncMock())
        music = MagicMock(is_active=lambda: False)
        stats = {'last_user_activity_at': 0, 'proactive_sent_since_user': False}
        loop = asyncio.create_task(bridge.proactive_idle_loop(
            gemini, stats, bridge.new_speech_state(), music,
            idle_after=0, check_every=0.005, learning_visual_state=state))
        try:
            await asyncio.sleep(0.025)
            gemini.send.assert_not_awaited()
        finally:
            loop.cancel()
            await asyncio.gather(loop, return_exceptions=True)


if __name__ == '__main__':
    unittest.main()
