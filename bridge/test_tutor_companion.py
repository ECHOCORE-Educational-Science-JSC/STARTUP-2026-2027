"""Learner memories and proactive invitations use evidence and respect quiet time."""
import asyncio
import io
import inspect
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import bridge
import learning_image as images


class LearnerMemoryTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory(dir='test-tmp'))
        self.path = Path(directory) / 'memory.json'
        self.memory = bridge.PersistentMemory(self.path)

    def remember_progress(self, **overrides):
        fields = dict(learner='Bo', skill='grammar', topic='past simple', level='A2',
                      evidence="Bé nói 'I goed', rồi tự sửa thành 'I went'.",
                      next_step='Ôn ba động từ bất quy tắc', status='practising')
        fields.update(overrides)
        return self.memory.remember_learning_progress(**fields)

    def test_learning_evidence_survives_restart_with_learner_and_next_step(self):
        self.assertTrue(self.remember_progress()['saved'])
        reloaded = bridge.PersistentMemory(self.path)
        self.assertEqual(reloaded.items[0]['kind'], 'learning')
        self.assertEqual(reloaded.items[0]['learner'], 'Bo')
        self.assertEqual(reloaded.items[0]['level'], 'A2')
        self.assertIn('I went', reloaded.prompt_context(query='past simple'))
        self.assertIn('bất quy tắc', reloaded.prompt_context(query='past simple'))

    def test_missing_evidence_or_unconfirmed_identity_does_not_invent_profile(self):
        for fields in ({'evidence': ''}, {'learner': ''}, {'level': 'C2'}, {'skill': 'IQ'}):
            with self.subTest(fields=fields):
                self.assertFalse(self.remember_progress(**fields)['saved'])
        self.assertEqual(self.memory.items, [])

    def test_repeated_same_observation_is_not_saved_twice(self):
        self.remember_progress()
        self.assertTrue(self.remember_progress()['duplicate'])
        self.assertEqual(len(self.memory.items), 1)

    def test_updated_progress_preserves_history_but_context_uses_latest_status(self):
        self.remember_progress()
        self.remember_progress(evidence='Tự dùng I went đúng trong hai ví dụ mới.', status='improving')
        self.assertEqual(len(bridge.PersistentMemory(self.path).items), 2)
        context = self.memory.prompt_context(query='past simple')
        self.assertIn('improving', context)
        self.assertNotIn("I goed", context)

    def test_two_children_have_separate_learning_evidence(self):
        self.remember_progress()
        self.remember_progress(learner='An', evidence='Bé chưa dùng được quá khứ.', level='A1')
        reloaded = bridge.PersistentMemory(self.path)
        self.assertEqual({item['learner'] for item in reloaded.items}, {'Bo', 'An'})
        self.assertIn('Do not assume', reloaded.prompt_context())

    def test_large_memory_keeps_archive_and_retrieves_old_relevant_fact_with_bounded_prompt(self):
        self.memory.items = [{'fact': 'Bé Bo thích khủng long.', 'saved_at': '2025'}] + [
            {'fact': f'Bé Bo học ví dụ khác số {i}.', 'saved_at': '2026'} for i in range(2100)]
        self.memory.remember('Bé Bo thích trò đoán từ.')
        reloaded = bridge.PersistentMemory(self.path)
        self.assertGreater(len(reloaded.items), 2100)
        context = reloaded.prompt_context(query='khủng long')
        self.assertIn('khủng long', context)
        self.assertLessEqual(len(context), 12000)
        self.assertLessEqual(context.count('\n- '), 48)

    def test_delete_progress_and_reject_secrets_in_evidence(self):
        self.assertFalse(self.remember_progress(evidence='API key abc123')['saved'])
        self.remember_progress()
        self.assertEqual(self.memory.forget('past simple')['deleted'], 1)
        self.assertEqual(bridge.PersistentMemory(self.path).items, [])

    def test_explicit_recall_finds_archived_details_for_only_the_requested_child(self):
        self.remember_progress()
        self.remember_progress(learner='An', evidence='An cần luyện quá khứ.')
        self.memory.remember('Bo thích khủng long.')
        rows = self.memory.recall(query='past simple', learner='Bo')['memories']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['learner'], 'Bo')
        self.assertIn('I went', rows[0]['evidence'])
        self.assertEqual(self.memory.recall(query='unseen penguin')['memories'], [])


class ProactiveTutorTest(unittest.IsolatedAsyncioTestCase):
    async def run_idle(self, stats=None, speech=None, visual=None, active=False, memory=None):
        events = []
        async def send(message):
            events.append(json.loads(message))
            stats['assistant_response_pending'] = False  # Completed model reply in this probe.
        stats = stats if stats is not None else {'last_user_activity_at': 0}
        task = asyncio.create_task(bridge.proactive_idle_loop(
            MagicMock(send=send), stats, speech or bridge.new_speech_state(),
            MagicMock(is_active=lambda: active), idle_after=0, check_every=.002,
            followup_after=.008, learning_visual_state=visual, memory_store=memory))
        try:
            await asyncio.sleep(.035)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return events

    async def test_invites_then_gives_one_hint_and_stops_without_spamming(self):
        events = await self.run_idle({'last_user_activity_at': 0, 'lesson_active': True})
        self.assertEqual(len(events), 2)
        self.assertIn('gentle hint', events[1]['clientContent']['turns'][0]['parts'][0]['text'])

    async def test_busy_or_quiet_modes_never_create_autonomous_turn(self):
        for flag in ('charging', 'greeting_pending', 'assistant_speaking',
                     'assistant_response_pending', 'proactive_paused', 'visual_work_pending'):
            with self.subTest(flag=flag):
                self.assertEqual(await self.run_idle({'last_user_activity_at': 0, flag: True}), [])
        self.assertEqual(await self.run_idle(active=True), [])
        self.assertEqual(await self.run_idle(speech={'started': True, 'closed': False}), [])

    async def test_recent_assistant_reply_restarts_quiet_timer(self):
        events = []
        gemini = MagicMock(send=AsyncMock(side_effect=lambda data: events.append(data)))
        stats = {'last_user_activity_at': 0, 'last_assistant_activity_at': time.monotonic()}
        task = asyncio.create_task(bridge.proactive_idle_loop(
            gemini, stats, bridge.new_speech_state(), MagicMock(is_active=lambda: False),
            idle_after=1, check_every=.002))
        try:
            await asyncio.sleep(.02)
            self.assertEqual(events, [])
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_live_memory_and_recent_subject_are_supplied_as_facts_only(self):
        memory = MagicMock(prompt_context=lambda **kwargs: '\nFACT: Bo likes dinosaurs.')
        events = await self.run_idle({'last_user_activity_at': 0, 'last_input_text': 'Ôn dinosaur'}, memory=memory)
        text = events[0]['clientContent']['turns'][0]['parts'][0]['text']
        self.assertIn('dinosaurs', text)
        self.assertIn('Ôn dinosaur', text)
        self.assertIn('facts only', text)

    async def test_new_proactive_picture_does_not_inherit_old_exact_image_request(self):
        visual = bridge.learning_session.LearningVisualState()
        visual.observe_user('Cho xem con mèo màu cam')
        visual.finish_turn()
        await self.run_idle(visual=visual)
        self.assertEqual(visual.authoritative_visual_request('dog', 'one brown dog'), ('dog', 'one brown dog'))

    async def test_speech_starting_during_memory_lookup_cancels_invitation(self):
        stats = {'last_user_activity_at': 0}
        speech = bridge.new_speech_state()
        def lookup(**kwargs):
            speech['started'] = True
            speech['closed'] = False
            stats['last_user_activity_at'] = time.monotonic()
            return 'facts'
        self.assertEqual(await self.run_idle(stats, speech=speech, memory=MagicMock(prompt_context=lookup)), [])

    def test_default_invitation_is_faster_and_user_can_pause_or_resume(self):
        self.assertLessEqual(inspect.signature(bridge.proactive_idle_loop).parameters['idle_after'].default, 25)
        stats = {'proactive_count': 2, 'proactive_sent_since_user': True}
        bridge.update_tutor_activity(stats, 'Đừng nói nữa, cho bé yên lặng nhé')
        self.assertTrue(stats['proactive_paused'])
        bridge.update_tutor_activity(stats, 'Học tiếng Anh tiếp đi')
        self.assertFalse(stats['proactive_paused'])
        self.assertTrue(stats['lesson_active'])
        self.assertEqual(stats['proactive_count'], 0)


class FastThumbnailTest(unittest.TestCase):
    def test_next_related_lesson_word_can_prefetch_without_replacing_current_picture(self):
        state = bridge.learning_session.LearningVisualState()
        state.observe_user('Dạy tiếng Anh con mèo màu cam')
        state.active = True
        self.assertEqual(state.prefetch_visual_request('dog', 'one brown dog'), ('dog', 'one brown dog'))
        self.assertEqual(state.turn_word, 'cat')
        with self.assertRaises(images.LearningImageError):
            state.authoritative_visual_request('dog', 'one brown dog')
        with self.assertRaises(images.LearningImageError):
            state.prefetch_visual_request('airplane', 'airplane photo')

    def test_thumbnail_is_prepared_first_without_waiting_for_large_original(self):
        candidate = {'url': 'https://example.org/large.jpg', 'thumbnail': 'https://example.org/thumb.jpg'}
        with patch.object(images, '_read_url', return_value=b'photo') as read, \
             patch.object(images, 'make_learning_png', return_value=b'final png'):
            result = images._download_google_candidate(candidate, time.monotonic() + 10)
        self.assertEqual(read.call_args.args[0], candidate['thumbnail'])
        self.assertEqual(result[0]['url'], candidate['thumbnail'])

    def test_unreadable_thumbnail_falls_back_to_original_before_pixel_verification(self):
        candidate = {'url': 'https://example.org/large.jpg', 'thumbnail': 'https://example.org/thumb.jpg'}
        with patch.object(images, '_read_url', side_effect=[OSError('thumbnail blocked'), b'original']) as read, \
             patch.object(images, 'make_learning_png', return_value=b'final png'):
            result = images._download_google_candidate(candidate, time.monotonic() + 10)
        self.assertEqual([call.args[0] for call in read.call_args_list],
                         [candidate['thumbnail'], candidate['url']])
        self.assertEqual(result[0]['url'], candidate['url'])


class MemoryToolFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_proactive_invitation_cannot_invent_progress_or_start_music(self):
        replies = []
        class Gemini:
            def __aiter__(self):
                async def events():
                    yield json.dumps({'toolCall': {'functionCalls': [
                        {'id': str(index), 'name': name, 'args': {}} for index, name in enumerate((
                            'remember_user_fact', 'remember_learning_progress', 'play_song', 'adjust_volume'))]}})
                    yield json.dumps({'serverContent': {'turnComplete': True}})
                return events()
            async def send(self, data): replies.append(json.loads(data))
        device, memory = MagicMock(send=AsyncMock()), MagicMock()
        memory.remember.return_value = {'saved': True}
        memory.remember_learning_progress.return_value = {'saved': True}
        controller = MagicMock(is_active=lambda: False, is_playing=lambda: False)
        controller.prepare, controller.schedule_pending = AsyncMock(), AsyncMock()
        controller.prepare.side_effect = AssertionError('A proactive event must not start a song')
        await bridge.gemini_output(Gemini(), device, None, None, 's', 1,
                                  {'gemini_content_seen': False, 'proactive_turn': True}, bridge.new_speech_state(),
                                  music_controller=controller, memory_store=memory)
        responses = [item['response'] for event in replies
                     for item in event.get('toolResponse', {}).get('functionResponses', [])]
        self.assertEqual(len(responses), 4)
        self.assertTrue(all('error' in response for response in responses))
        memory.remember.assert_not_called()
        memory.remember_learning_progress.assert_not_called()
        controller.prepare.assert_not_awaited()
        self.assertFalse(any(json.loads(call.args[0]).get('type') == 'volume' for call in device.send.call_args_list))

    async def test_progress_and_recall_tools_reach_real_persistent_store(self):
        directory = self.enterContext(tempfile.TemporaryDirectory(dir='test-tmp'))
        memory = bridge.PersistentMemory(Path(directory) / 'memory.json')
        replies = []
        fields = dict(learner='Bo', skill='grammar', topic='past simple', level='A2',
                      evidence='Bo tự sửa I goed thành I went.', next_step='Ôn went và ate.', status='improving')
        class Gemini:
            def __aiter__(self):
                async def events():
                    yield json.dumps({'toolCall': {'functionCalls': [
                        {'id': 'save', 'name': 'remember_learning_progress', 'args': fields},
                        {'id': 'recall', 'name': 'recall_user_memories', 'args': {'query': 'past simple', 'learner': 'Bo'}}]}})
                    yield json.dumps({'serverContent': {'turnComplete': True}})
                return events()
            async def send(self, data): replies.append(json.loads(data))
        device = MagicMock(send=AsyncMock())
        music = MagicMock(is_active=lambda: False, is_playing=lambda: False)
        music.schedule_pending = AsyncMock()
        await bridge.gemini_output(Gemini(), device, None, None, 's', 1,
                                  {'gemini_content_seen': False}, bridge.new_speech_state(),
                                  music_controller=music, memory_store=memory)
        responses = {item['id']: item['response'] for event in replies
                     for item in event.get('toolResponse', {}).get('functionResponses', [])}
        self.assertTrue(responses['save']['result']['saved'])
        self.assertEqual(responses['recall']['result']['memories'][0]['learner'], 'Bo')
        self.assertEqual(len(bridge.PersistentMemory(memory.path).items), 1)


if __name__ == '__main__':
    unittest.main()
