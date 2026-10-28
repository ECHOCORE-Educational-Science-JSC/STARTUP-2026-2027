"""Keep successful visuals stable through response continuations, not new requests."""
import unittest
from unittest.mock import AsyncMock, MagicMock
import bridge
import learning_session


class VisualDeliveryStateTest(unittest.IsolatedAsyncioTestCase):
    @unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
    async def test_revisiting_cached_vocabulary_redraws_the_current_screen(self):
        state = learning_session.LearningVisualState()
        loader = MagicMock()
        loader.get = AsyncMock(side_effect=[
            {'png': b'cat pixels', 'verified': True},
            {'png': b'dog pixels', 'verified': True},
        ])
        device = MagicMock(send=AsyncMock())
        await bridge.deliver_learning_image(device, 's', state, 'key', 'cat', 'cat', prefetch=loader)
        await bridge.deliver_learning_image(device, 's', state, 'key', 'dog', 'dog', prefetch=loader)
        await bridge.deliver_learning_image(device, 's', state, 'key', 'cat', 'cat', prefetch=loader)
        self.assertEqual(loader.get.await_count, 2, 'Revisiting a verified word must not search again')
        self.assertEqual(device.send.await_count, 3, 'The robot currently shows dog, so cat must be redrawn')

    @unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
    async def test_success_survives_model_turn_end_and_rephrased_dish_tool(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Cho xem chân gà xào sả ớt trên đĩa trắng')
        loader = MagicMock()
        loader.get = AsyncMock(return_value={'png': b'verified cooked dish', 'verified': True})
        device = MagicMock(send=AsyncMock())
        first = await bridge.deliver_learning_image(device, 's', state, 'key', 'chan ga', 'chan ga', prefetch=loader)
        state.finish_turn()
        loader.get.side_effect = bridge.learning_image.LearningImageError('SERPAPI_TIMEOUT_OR_NETWORK')
        repeated = await bridge.deliver_learning_image(device, 's', state, 'key', 'chicken',
            'a plate of stir-fried chicken feet with lemongrass and chili', prefetch=loader)
        self.assertEqual(repeated['png'], first['png'])
        self.assertEqual(loader.get.await_count, 1)
        self.assertEqual(device.send.await_count, 1)

    @unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
    async def test_new_user_request_must_not_reuse_conflicting_color(self):
        state = learning_session.LearningVisualState()
        loader = MagicMock()
        loader.get = AsyncMock(return_value={'png': b'orange cat', 'verified': True})
        device = MagicMock(send=AsyncMock())
        state.observe_user('Cho xem con mèo màu cam')
        await bridge.deliver_learning_image(device, 's', state, 'key', 'cat', 'orange cat', prefetch=loader)
        state.finish_turn()
        state.observe_user('Cho xem con mèo màu đen')
        loader.get.side_effect = bridge.learning_image.LearningImageError('GOOGLE_NO_VERIFIED_MATCH')
        with self.assertRaises(bridge.learning_image.LearningImageError):
            await bridge.deliver_learning_image(device, 's', state, 'key', 'cat', 'black cat', prefetch=loader)
        self.assertEqual(loader.get.await_count, 2)

    def test_cooked_dish_has_precise_identity_and_english_meaning(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Cho xem chân gà xào sả ớt')
        word, query = state.authoritative_visual_request('chicken', 'chicken')
        self.assertEqual(word, 'chan ga xao sa ot')
        prompt = bridge.learning_image._verification_prompt(query, word)
        self.assertIn('stir-fried chicken feet', prompt)

    def test_concrete_assistant_explanation_is_visual_in_normal_conversation(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Explain what happens in a garden')
        state.observe_assistant('Butterflies visit the flowers to drink nectar.')
        self.assertEqual(state.turn_word, 'butterfly')
        self.assertIsNotNone(state.correction_prompt())

    def test_music_and_unclear_hearing_cannot_trigger_proactive_pictures(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Phát nhạc của ban nhạc The Animals')
        state.observe_assistant('Bee means con ong')
        self.assertIsNone(state.correction_prompt())
        state.finish_turn()
        state.observe_user('tôi nói chưa rõ')
        state.request_clarification()
        state.observe_assistant('Apple là quả táo')
        self.assertIsNone(state.correction_prompt())
        self.assertEqual(state.prefetch_requests(), [])

    def test_known_plural_nouns_are_visual_subjects_in_explanations(self):
        for plural, singular in (
                ('butterflies', 'butterfly'), ('apples', 'apple'),
                ('buses', 'bus'), ('strawberries', 'strawberry'), ('tomatoes', 'tomato')):
            with self.subTest(plural=plural):
                state = learning_session.LearningVisualState()
                state.observe_user('Explain what happens outside')
                state.observe_assistant(f'{plural.capitalize()} are interesting to learn about.')
                self.assertEqual(state.turn_word, singular)
                self.assertIn(singular, state.correction_prompt())

    def test_plural_detection_does_not_guess_unknown_words(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Explain what happens outside')
        state.observe_assistant('The latest news is interesting.')
        self.assertIsNone(state.turn_word)
        self.assertIsNone(state.correction_prompt())

    def test_assistant_unclear_hearing_stops_picture_actions(self):
        for clarification in (
                'Wisio chưa nghe rõ, bé nhắc lại giúp mình nhé?',
                'Mình nghe chưa rõ câu hỏi, bé nói lại nhé?',
                "I didn't catch what you said. Could you say that again?",
                'Chưa nghe rõ, bé nói lại giúp Wisio nhé.'):
            with self.subTest(clarification=clarification):
                state = learning_session.LearningVisualState()
                state.observe_user('Dạy các từ cat và dog')
                old_epoch = state.request_epoch
                state.observe_assistant(clarification)
                self.assertTrue(state.waiting_for_clarification)
                self.assertGreater(state.request_epoch, old_epoch)
                self.assertIsNone(state.correction_prompt())
                self.assertEqual(state.prefetch_requests(), [])
                self.assertIsNone(state.fallback_request())
                with self.assertRaises(bridge.learning_image.LearningImageError):
                    state.authoritative_visual_request('cat', 'one cat')
                state.finish_turn()
                state.observe_assistant('Apple là quả táo.')
                self.assertIsNone(state.correction_prompt())
                self.assertTrue(state.waiting_for_clarification)

    def test_lesson_repeat_instruction_is_not_unclear_hearing(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Dạy tiếng Anh cho bé')
        state.observe_assistant('Bé nhắc lại từ elephant nhé!')
        self.assertFalse(state.waiting_for_clarification)
        self.assertEqual(state.turn_word, 'elephant')
        self.assertIsNotNone(state.correction_prompt())

    def test_incremental_clarification_blocks_guessed_image(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Con mèo hay cái gì đó')
        state.observe_assistant('Wisio chưa nghe rõ,')
        state.observe_assistant('bé nhắc lại giúp mình nhé?')
        self.assertTrue(state.waiting_for_clarification)
        self.assertIsNone(state.correction_prompt())
        with self.assertRaises(bridge.learning_image.LearningImageError):
            state.authoritative_visual_request('cat', 'cat')

    def test_clarification_fragments_do_not_cross_separate_model_turns(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Dạy tiếng Anh con voi')
        state.observe_assistant('Con voi nghe không rõ khi có tiếng ồn.')
        state.finish_turn()
        state.observe_user('Dạy từ elephant')
        state.observe_assistant('Bé nhắc lại từ elephant nhé!')
        self.assertFalse(state.waiting_for_clarification)

    def test_animal_hearing_explanation_is_not_assistant_clarification(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Dạy tiếng Anh con voi')
        state.observe_assistant('Con voi nghe không rõ khi có tiếng ồn.')
        self.assertFalse(state.waiting_for_clarification)
        self.assertEqual(state.turn_word, 'elephant')
        self.assertIsNotNone(state.correction_prompt())

    def test_animal_hearing_followed_by_lesson_repeat_does_not_pause_actions(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Dạy tiếng Anh con voi')
        state.observe_assistant('Con voi nghe không rõ khi có tiếng ồn.')
        state.observe_assistant('Bé nhắc lại từ elephant nhé!')
        self.assertFalse(state.waiting_for_clarification)
        self.assertIsNotNone(state.correction_prompt())

    def test_clarifying_user_answer_replaces_unclear_request_before_turn_end(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Cho xem ảnh con mèo màu cam')
        state.mark_image('cat', 'one orange cat photo', {'png': b'orange cat', 'verified': True})
        state.request_clarification()
        state.observe_user('Cho xem ảnh con chó màu đen')
        self.assertFalse(state.waiting_for_clarification)
        self.assertIsNone(state.shown_image('cat', 'one orange cat photo'))
        word, query = state.authoritative_visual_request('dog', 'dog')
        self.assertEqual(word, 'dog')
        self.assertIn('black', query)
        self.assertNotIn('orange', query)
        self.assertIsNotNone(state.correction_prompt())

    def test_empty_transcription_preserves_latest_request_and_success(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Cho xem chân gà xào sả ớt trên đĩa trắng')
        word, query = state.authoritative_visual_request('chicken', 'chicken')
        state.mark_image(word, query, {'png': b'cooked dish', 'verified': True})
        epoch = state.request_epoch
        state.finish_turn()
        state.observe_user('  ')
        self.assertEqual(state.request_epoch, epoch)
        self.assertEqual(state.authoritative_visual_request('chicken', 'chicken'), (word, query))
        self.assertEqual(state.shown_image(word, query)['png'], b'cooked dish')


if __name__ == '__main__':
    unittest.main()
