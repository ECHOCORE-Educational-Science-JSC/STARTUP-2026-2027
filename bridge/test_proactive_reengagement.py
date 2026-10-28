"""Quiet microphones must allow fresh invitations after a real cooldown."""
import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

import bridge


class ProactiveReengagementTest(unittest.IsolatedAsyncioTestCase):
    async def collect(self, stats=None, stop_after=3):
        stats = stats if stats is not None else {'last_user_activity_at': 0}
        messages, times = [], []
        finished = asyncio.Event()
        async def send(raw):
            messages.append(json.loads(raw))
            times.append(time.monotonic())
            # Simulate a completed spoken answer, not ongoing model generation.
            stats['assistant_response_pending'] = False
            stats['last_assistant_activity_at'] = time.monotonic()
            stats['proactive_last_spoken_text'] = 'The dinosaur is big. Big or small?'
            if len(messages) >= stop_after:
                stats['proactive_paused'] = True
                finished.set()
        task = asyncio.create_task(bridge.proactive_idle_loop(
            MagicMock(send=send), stats, bridge.new_speech_state(),
            MagicMock(is_active=lambda: False), idle_after=0, check_every=.002,
            followup_after=.008, reengage_after=.035,
            learning_visual_state=bridge.learning_session.ConversationState()))
        try:
            await asyncio.wait_for(finished.wait(), .8)
            await asyncio.sleep(.01)
            self.assertFalse(task.done())
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return messages, times, stats

    async def test_long_quiet_restarts_conversation_instead_of_waiting_forever(self):
        messages, times, stats = await self.collect()
        self.assertEqual(len(messages), 3)
        self.assertGreaterEqual(times[2] - times[1], .035)
        texts = [m['clientContent']['turns'][0]['parts'][0]['text'] for m in messages]
        self.assertIn('gentle hint', texts[1])
        self.assertNotEqual(texts[0], texts[2])
        self.assertIn('fresh', texts[2].lower())
        self.assertIn('Big or small?', texts[2])
        self.assertIn('facts only', texts[2])
        self.assertFalse(any('toolCall' in m for m in messages))

    async def test_idle_microphone_open_without_speech_does_not_block_invitation(self):
        messages, _, _ = await self.collect({'last_user_activity_at': 0,
                                            'listen_events': 99, 'input_frames': 999}, stop_after=1)
        self.assertEqual(len(messages), 1)

    async def test_occasional_quote_reaches_model_without_changing_short_turn_rules(self):
        messages, _, stats = await self.collect({'last_user_activity_at': 0,
                                                'proactive_invitation_index': 3}, stop_after=1)
        text = messages[0]['clientContent']['turns'][0]['parts'][0]['text']
        self.assertIn('Benjamin Franklin', text)
        self.assertIn('if it fits the recent conversation', text)
        self.assertIn('ask one question, then wait', text)
        self.assertFalse(any('toolCall' in message for message in messages))

    async def test_explicit_quiet_still_blocks_all_later_cycles(self):
        stats = {'last_user_activity_at': 0, 'proactive_count': 2, 'last_proactive_at': 0}
        bridge.update_tutor_activity(stats, 'Wisio im lặng nhé')
        stats['last_user_activity_at'] = 0
        gemini = MagicMock(send=AsyncMock())
        task = asyncio.create_task(bridge.proactive_idle_loop(
            gemini, stats, bridge.new_speech_state(), MagicMock(is_active=lambda: False),
            idle_after=0, check_every=.002, followup_after=.004, reengage_after=.008))
        try:
            await asyncio.sleep(.04)
            gemini.send.assert_not_awaited()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_variation_survives_new_user_activity_but_round_limits_reset(self):
        stats = {'last_user_activity_at': 0, 'proactive_count': 2,
                 'proactive_invitation_index': 2}
        bridge.update_tutor_activity(stats, 'Mình học tiếng Anh tiếp nhé')
        self.assertEqual(stats['proactive_count'], 0)
        messages, _, _ = await self.collect(stats, stop_after=1)
        self.assertEqual(len(messages), 1)
        self.assertGreater(stats['proactive_invitation_index'], 2)

    async def test_previous_invitation_is_collected_from_actual_output_transcript(self):
        class Gemini:
            def __aiter__(self):
                async def events():
                    yield json.dumps({'serverContent': {'outputTranscription': {'text': 'The dinosaur is big.'}}})
                    yield json.dumps({'serverContent': {'outputTranscription': {'text': 'Big or small?'}}})
                    yield json.dumps({'serverContent': {'turnComplete': True}})
                return events()
        stats = {'gemini_content_seen': False, 'proactive_turn': True}
        controller = MagicMock(is_active=lambda: False, is_playing=lambda: False,
                               schedule_pending=AsyncMock())
        await bridge.gemini_output(
            Gemini(), MagicMock(send=AsyncMock()), None, None, 's', 1,
            stats, bridge.new_speech_state(), music_controller=controller)
        self.assertEqual(stats['proactive_last_spoken_text'], 'The dinosaur is big. Big or small?')


if __name__ == '__main__':
    unittest.main()
