"""Keep conversational suggestion requests out of visual search descriptions."""
import unittest
from unittest.mock import patch

import learning_image as images


SUGGESTION_REQUEST = (
    'chan ga; user scene: chan ga a khong biet ban co the goi y cho toi '
    'mot vai mon duoc khong'
)
DESCRIPTION_REQUEST = (
    'ban thu mieu ta cho toi mot vai mon chan ga di toi cung chua bao gio '
    'an may cai do photo'
)


class QuerySemanticsTest(unittest.TestCase):
    def test_suggestion_dialogue_is_not_an_image_attribute(self):
        self.assertEqual(images.google_search_query(SUGGESTION_REQUEST, 'chan ga'),
                         'chân gà món ăn')

    def test_description_dialogue_keeps_photo_and_explicit_food_context(self):
        self.assertEqual(images.google_search_query(DESCRIPTION_REQUEST, 'chan ga'),
                         'chân gà món ăn photo')

    def test_cooked_dish_and_serving_details_survive_suggestion_tail(self):
        query = ('Cho tôi xem chân gà xào sả ớt trên đĩa trắng, '
                 'bạn có thể gợi ý cho tôi vài món được không? photo')
        self.assertEqual(images.google_search_query(query, 'chan ga xao sa ot'),
                         'chân gà xào sả ớt trên đĩa trắng photo')

    def test_count_color_breed_and_accessories_survive_english_suggestion_tail(self):
        query = ('Show me two orange Siamese cats wearing blue scarves beside a vase, '
                 'could you suggest names please? cartoon')
        self.assertEqual(images.google_search_query(query, 'cat'),
                         'two orange Siamese cats wearing blue scarves beside a vase cartoon')

    def test_unknown_visual_attributes_are_not_filtered_by_a_word_allowlist(self):
        query = 'con mèo tam thể đeo kính phi công và khăn lụa đỏ bên bình hoa photo'
        self.assertEqual(images.google_search_query(query, 'cat'), query)

    def test_plain_subject_does_not_invent_a_cooking_method_or_food_context(self):
        self.assertEqual(images.google_search_query('chan ga photo', 'chan ga'),
                         'chân gà photo')

    def test_original_full_request_still_reaches_pixel_verification(self):
        candidate = {'url': 'https://example.org/food.png', 'title': 'Food', 'google_position': 1}
        with patch.object(images.google_image_search, 'search_images', return_value=[candidate]) as search, \
             patch.object(images, '_download_google_candidate', return_value=(candidate, b'pixels')), \
             patch.object(images, 'verify_image_candidates', return_value=[0]) as verify:
            result = images._prepare_google_learning_image(DESCRIPTION_REQUEST, 'fake-gemini',
                                                          'chan ga', 'fake-serpapi')
        self.assertEqual(search.call_args.args[0], 'chân gà món ăn photo')
        self.assertEqual(verify.call_args.args, ([b'pixels'], DESCRIPTION_REQUEST, 'chan ga', 'fake-gemini'))
        self.assertEqual(result['png'], b'pixels')


if __name__ == '__main__':
    unittest.main()
