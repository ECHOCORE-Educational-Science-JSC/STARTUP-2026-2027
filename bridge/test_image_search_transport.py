"""Search transport selection must keep query safety, caching and request bounds."""
import json
import os
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch

import google_image_search as google


def response(payload):
    result = MagicMock()
    result.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return result


class GoogleImageTransportTest(unittest.TestCase):
    def setUp(self):
        google.clear_search_cache()
        self.enterContext(patch.dict(os.environ, {
            'WISIO_GOOGLE_IMAGE_ENGINE': 'google_images_light', 'WISIO_IMAGE_SOURCE': 'auto'}))

    def test_default_engine_keeps_native_query_safe_landscape_and_localization(self):
        # Removing engine selection or its safety parameters must fail this test.
        os.environ.pop('WISIO_GOOGLE_IMAGE_ENGINE', None)
        with patch.object(google, 'urlopen', return_value=response({'images_results': []})) as send:
            google.search_images('nghêu hấp sả trong tô trắng', 'fake-key', timeout=3.5)
        params = parse_qs(urlsplit(send.call_args.args[0].full_url).query)
        self.assertEqual(params['engine'], ['google_images_light'])
        self.assertEqual(params['q'], ['nghêu hấp sả trong tô trắng'])
        self.assertEqual(params['safe'], ['active'])
        self.assertEqual(params['imgar'], ['w'])
        self.assertEqual(params['gl'], ['vn'])
        self.assertEqual(params['hl'], ['vi'])
        # Submission shares the wall-clock budget with archive retrieval.
        self.assertGreater(send.call_args.kwargs['timeout'], 0)
        self.assertLessEqual(send.call_args.kwargs['timeout'], 3.5)
        self.assertEqual(send.call_count, 1)

    def test_explicit_classic_engine_is_supported(self):
        with patch.dict(os.environ, {'WISIO_GOOGLE_IMAGE_ENGINE': ' GOOGLE_IMAGES '}), \
                patch.object(google, 'urlopen', return_value=response({'images_results': []})) as send:
            google.search_images('orange cat', 'fake-key')
        params = parse_qs(urlsplit(send.call_args.args[0].full_url).query)
        self.assertEqual(params['engine'], ['google_images'])

    def test_invalid_engine_fails_before_network_and_configuration_key_lookup(self):
        for engine in ('', 'bing_images', 'google_images?api_key=SECRET'):
            with self.subTest(engine=engine), \
                    patch.dict(os.environ, {'WISIO_GOOGLE_IMAGE_ENGINE': engine}), \
                    patch.object(google, 'urlopen') as send, \
                    patch.object(google, 'get_api_key') as key:
                with self.assertRaisesRegex(google.GoogleImageSearchError, 'SERPAPI_ENGINE_CONFIG') as caught:
                    google.search_images('cat', 'fake-key')
                self.assertNotIn('SECRET', str(caught.exception))
                self.assertIn('SERPAPI_ENGINE_CONFIG', google.configuration_status())
                send.assert_not_called()
                key.assert_not_called()

    def test_metadata_cache_is_separate_for_light_and_classic_engines(self):
        def serve(request, **_):
            engine = parse_qs(urlsplit(request.full_url).query)['engine'][0]
            return response({'images_results': [{'original': f'https://example.org/{engine}.jpg'}]})

        with patch.object(google, 'urlopen', side_effect=serve) as send:
            light = google.search_images('cat', 'fake-key')
            with patch.dict(os.environ, {'WISIO_GOOGLE_IMAGE_ENGINE': 'google_images'}):
                classic = google.search_images('cat', 'fake-key')
                self.assertEqual(google.search_images('cat', 'fake-key'), classic)
            self.assertEqual(google.search_images('cat', 'fake-key'), light)
        self.assertEqual(send.call_count, 2)
        self.assertNotEqual(light[0]['url'], classic[0]['url'])

    def test_light_payload_preserves_candidate_urls_dimensions_and_relevance(self):
        payload = {'images_results': [{
            'original': 'https://example.org/seafood.jpg',
            'thumbnail': 'https://example.org/seafood-small.jpg',
            'link': 'https://example.org/seafood',
            'title': 'Hải sản trong đĩa trắng',
            'original_width': 960, 'original_height': 720,
        }]}
        with patch.object(google, 'urlopen', return_value=response(payload)):
            candidates = google.search_images('hải sản trong đĩa trắng', 'fake-key')
        self.assertEqual(candidates, [{
            'url': 'https://example.org/seafood.jpg',
            'thumbnail': 'https://example.org/seafood-small.jpg',
            'page_url': 'https://example.org/seafood',
            'title': 'Hải sản trong đĩa trắng',
            'google_position': 1, 'width': 960, 'height': 720,
        }])

    def test_timeout_does_not_retry_or_start_a_second_engine_request(self):
        with patch.object(google, 'urlopen', side_effect=TimeoutError('SECRET')) as send:
            with self.assertRaisesRegex(google.GoogleImageSearchError, 'reason=TIMEOUT') as caught:
                google.search_images('cat', 'fake-key')
        self.assertEqual(send.call_count, 1)
        self.assertNotIn('SECRET', str(caught.exception))

    def test_configuration_identifies_selected_engine_without_secrets(self):
        with patch.object(google, 'get_api_key', return_value='SECRET'):
            status = google.configuration_status()
            self.assertIn('google_images_light', status)
            self.assertNotIn('SECRET', status)
            with patch.dict(os.environ, {'WISIO_GOOGLE_IMAGE_ENGINE': 'google_images'}):
                self.assertIn('engine=google_images;', google.configuration_status())


if __name__ == '__main__':
    unittest.main()
