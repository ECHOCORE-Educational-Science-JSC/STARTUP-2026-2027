"""Food context must not become a beach or clothing illustration."""
import unittest
from unittest.mock import patch

import learning_image as images
from learning_session import LearningVisualState


REQUEST = 'Bạn hãy cho tôi một vài món ăn kiểu như đồ biển á'


class FoodContextTest(unittest.TestCase):
    def test_vietnamese_seafood_request_is_not_a_sea_scene(self):
        state = LearningVisualState()
        state.observe_user(REQUEST)
        self.assertEqual(state.turn_word, 'seafood')
        word, query = state.authoritative_visual_request('sea', 'one sea')
        self.assertEqual(word, 'seafood')
        self.assertEqual(images.google_search_query(query, word), 'hải sản món ăn photo')
        self.assertIn(REQUEST, query)

    def test_specific_seafood_is_allowed_but_stays_food(self):
        state = LearningVisualState()
        state.observe_user(REQUEST)
        word, query = state.authoritative_visual_request('shrimp', 'grilled shrimp on a white plate photo')
        self.assertEqual(word, 'shrimp')
        self.assertIn('grilled shrimp on a white plate photo', query)
        self.assertIn('seafood dish', query)
        with self.assertRaises(images.LearningImageError):
            state.authoritative_visual_request('bikini', 'beach outfit')

    def test_seafood_preserves_explicit_cartoon_and_serving_details(self):
        for request in ('Cho tôi xem hải sản trên đĩa trắng kiểu hoạt hình',
                        'Cho xem hai món đồ biển trên đĩa trắng, kiểu hoạt hình'):
            with self.subTest(request=request):
                state = LearningVisualState()
                state.observe_user(request)
                word, query = state.authoritative_visual_request('sea', 'sea photo')
                search = images.google_search_query(query, word)
                self.assertEqual(word, 'seafood')
                self.assertIn('cartoon', query)
                self.assertTrue('cartoon' in search or 'hoat hinh' in images.normalized_phrase(search))
                self.assertIn('đĩa trắng', search)
                self.assertNotIn('photo', query)
                if 'hai món' in request:
                    self.assertIn('hai mon', images.normalized_phrase(search))

    def test_genuine_sea_and_beachwear_requests_are_not_changed_into_food(self):
        for request in ('Cho xem biển xanh', 'Đi biển mặc gì, cho xem đồ đi biển mùa hè'):
            with self.subTest(request=request):
                state = LearningVisualState()
                state.observe_user(request)
                self.assertNotEqual(state.turn_word, 'seafood')

    def test_verifier_receives_explicit_edible_food_identity(self):
        state = LearningVisualState()
        state.observe_user(REQUEST)
        word, query = state.authoritative_visual_request('sea', 'sea photo')
        prompt = images._verification_prompt(query, word)
        self.assertIn('requested_food_category', prompt)
        self.assertIn('seafood', prompt)
        self.assertIn('beachwear', prompt)

    def test_obvious_beachwear_candidate_cannot_be_accepted_for_food(self):
        candidate = {'url': 'https://example.org/fashion.jpg', 'google_position': 1,
                     'title': 'Đi biển mặc gì đẹp? 15+ cách phối đồ đi biển nữ xinh, cá tính'}
        with patch.object(images.google_image_search, 'search_images', return_value=[candidate]), \
             patch.object(images, '_download_google_candidate', return_value=(candidate, b'wrong pixels')) as download, \
             patch.object(images, 'verify_image_candidates', return_value=[0]) as verify:
            with self.assertRaises(images.LearningImageError):
                images._prepare_google_learning_image('hải sản món ăn photo', 'fake', 'seafood', 'fake')
        download.assert_not_called()
        verify.assert_not_called()
