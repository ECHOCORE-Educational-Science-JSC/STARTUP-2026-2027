import unittest

import learning_session


class LearningVisualStateTest(unittest.TestCase):
    def test_vietnamese_lesson_request_requires_visual_for_concrete_word(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Dạy tiếng Anh cho bé đi")
        state.observe_assistant("Apple nghĩa là quả táo. Bé đọc theo Wisio nhé!")
        prompt = state.correction_prompt()
        self.assertIn("show_learning_image", prompt)
        self.assertIn("apple", prompt.casefold())
        self.assertIsNone(state.correction_prompt())

    def test_abstract_grammar_turn_does_not_require_image(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Mình luyện tiếng Anh nhé")
        state.observe_assistant("Hôm nay mình luyện thì hiện tại đơn và cách đặt câu hỏi.")
        self.assertIsNone(state.correction_prompt())

    def test_successful_image_satisfies_turn_and_avoids_immediate_repeat(self):
        state = learning_session.LearningVisualState()
        state.observe_user("learn English")
        state.observe_assistant("This is an elephant.")
        state.mark_image("elephant")
        self.assertIsNone(state.correction_prompt())
        state.finish_turn()
        state.observe_assistant("Elephant means con voi.")
        self.assertIsNone(state.correction_prompt())

    def test_stop_phrase_leaves_lesson_mode(self):
        state = learning_session.LearningVisualState()
        state.observe_user("dạy tiếng Anh")
        self.assertTrue(state.active)
        state.observe_user("thôi học tiếng Anh, đổi chủ đề")
        self.assertFalse(state.active)
        state.observe_assistant("Apple")
        self.assertIsNone(state.correction_prompt())

    def test_vietnamese_concrete_request_supplies_english_word(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Dạy tiếng Anh con voi")
        self.assertEqual(state.turn_word, "elephant")


if __name__ == "__main__":
    unittest.main()
