"""Concrete drink names and ambiguous speech must keep their real subjects."""

import unittest

import learning_image
from learning_session import LearningVisualState, vocabulary_prefetch_requests


class DrinkSubjectTests(unittest.TestCase):
    def test_kumquat_tea_question_selects_the_drink_instead_of_grammatical_star(self):
        state = LearningVisualState()
        state.observe_user('Vậy còn trà tắc thì sao?')
        self.assertEqual(state.turn_word, 'tra tac')
        word, query = state.automatic_request()
        self.assertEqual(word, 'tra tac')
        self.assertEqual(learning_image.google_search_query(query, word), 'trà tắc photo')

    def test_generic_model_tea_keeps_exact_drink_and_all_serving_attributes(self):
        state = LearningVisualState()
        state.observe_user('Cho xem hai ly trà tắc có đá trong ly thủy tinh, dạng hoạt hình.')
        word, query = state.authoritative_visual_request('tea', 'tea photo')
        self.assertEqual(word, 'tra tac')
        search = learning_image.google_search_query(query, word)
        self.assertIn('hai ly trà tắc', search)
        self.assertIn('co da trong ly thuy tinh', search)
        self.assertIn('cartoon', search)
        self.assertNotIn('photo', search)

    def test_common_compound_drinks_keep_their_whole_names(self):
        for text, expected in (
                ('Trà chanh là gì?', 'tra chanh'),
                ('Trà sữa là gì?', 'tra sua'),
                ('Trà đào là gì?', 'tra dao'),
                ('Cà phê là gì?', 'ca phe'),
                ('Nước cam là gì?', 'nuoc cam'),
                ('Nước chanh là gì?', 'nuoc chanh'),
                ('Nước dừa là gì?', 'nuoc dua'),
                ('Sữa tươi là gì?', 'sua tuoi')):
            with self.subTest(text=text):
                state = LearningVisualState()
                state.observe_user(text)
                self.assertEqual(state.turn_word, expected)

    def test_english_kumquat_tea_keeps_drink_identity(self):
        state = LearningVisualState()
        state.observe_user('What about kumquat tea?')
        self.assertEqual(state.turn_word, 'tra tac')

    def test_pixel_verifier_checks_the_beverage_not_a_solid_food_dish(self):
        import json
        prompt = learning_image._verification_prompt('tra tac trong ly thuy tinh photo', 'tra tac')
        subject = json.loads(prompt.split('Subject: ', 1)[1])
        self.assertEqual(subject['requested_drink'], 'Vietnamese kumquat tea')
        self.assertEqual(subject['requested_food_category'], 'beverage')
        self.assertNotIn('requested_dish', subject)
        self.assertIn('Reject fruit alone', prompt)

    def test_drink_vocabulary_list_does_not_split_drinks_into_fruit_or_dairy(self):
        requests = vocabulary_prefetch_requests('Dạy các từ trà tắc, trà sữa và nước cam')
        self.assertEqual([item['word'] for item in requests], ['tra tac', 'tra sua', 'nuoc cam'])

    def test_milk_in_a_general_food_lesson_is_not_relabelled_as_a_specific_drink(self):
        state = LearningVisualState()
        state.observe_user('Teach milk and rice')
        self.assertEqual(state.authoritative_visual_request('milk', 'milk'), ('milk', 'milk'))

    def test_equivalent_drink_questions_share_one_precise_search(self):
        queries = []
        for question in ('Vậy còn trà tắc thì sao?', 'Trà tắc là gì?', 'Cho xem trà tắc'):
            state = LearningVisualState()
            state.observe_user(question)
            queries.append(state.automatic_request())
        self.assertEqual(queries, [('tra tac', 'tra tac photo')] * 3)

    def test_ambiguous_or_unrecognized_utterance_does_not_guess_a_picture(self):
        for text in ('trả sổ hộ long á hả?', 'Vậy thì sao?', 'Hộ mình với nhé',
                     'Cái phố đó ở đâu?', 'Con sống ở đâu?', 'Hoa muốn học tiếng Anh'):
            with self.subTest(text=text):
                state = LearningVisualState()
                state.observe_user(text)
                self.assertIsNone(state.turn_word)
                self.assertIsNone(state.automatic_request())

    def test_explicit_stars_tigers_and_pho_remain_available(self):
        for text, expected in (('Cho xem ngôi sao', 'star'),
                               ('Cho xem con hổ', 'tiger'),
                               ('Hổ sống ở đâu?', 'tiger'),
                               ('Cho xem phở', 'pho'),
                               ('pho', 'pho')):
            with self.subTest(text=text):
                state = LearningVisualState()
                state.observe_user(text)
                self.assertEqual(state.turn_word, expected)


if __name__ == '__main__':
    unittest.main()
