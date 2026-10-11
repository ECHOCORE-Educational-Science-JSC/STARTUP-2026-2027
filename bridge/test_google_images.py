"""Google search, pixel selection and private configuration regressions."""
import base64
import io
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import unittest
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch

import learning_image as images
import google_image_search as google


FIELDS = ('matches_subject', 'matches_attributes', 'matches_image_type',
          'suitable_for_child', 'landscape_fit', 'subject_fully_visible')


def response(payload):
    result = MagicMock()
    result.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return result


def verdict_payload(verdict, finish='STOP'):
    return {'candidates': [{'finishReason': finish, 'content': {'parts': [
        {'thought': True, 'text': 'Private reasoning, not a JSON verdict'},
        {'text': json.dumps(verdict)}]}}]}


class GoogleSearchTest(unittest.TestCase):
    def setUp(self):
        google.clear_search_cache()

    def test_preserves_vietnamese_attributes_and_requests_safe_landscape(self):
        with patch.object(google, 'urlopen', return_value=response({'images_results': []})) as send:
            google.search_images('nghêu hấp sả trong tô, ảnh chụp', 'fake-key')
        params = parse_qs(urlsplit(send.call_args.args[0].full_url).query)
        self.assertEqual(params['q'], ['nghêu hấp sả trong tô, ảnh chụp'])
        self.assertEqual(params['engine'], ['google_images_light'])
        self.assertEqual(params['safe'], ['active'])
        self.assertEqual(params['imgar'], ['w'])
        self.assertEqual(params['gl'], ['vn'])

    def test_landscape_ranking_dedup_and_unsafe_filter(self):
        payload = {'images_results': [
            {'original': 'https://example.org/portrait.jpg', 'original_width': 400, 'original_height': 800},
            {'original': 'https://example.org/wide.jpg', 'original_width': 800, 'original_height': 600},
            {'original': 'https://example.org/wide.jpg'},
            {'original': 'https://example.org/unsafe.jpg', 'unsafe': True},
            {'original': 'file:///C:/secret'}, {'original': 'http://127.0.0.1/a'},
            {'original': 'https://localhost/a'}, {'original': 'https://user:pass@example.org/a'}]}
        with patch.object(google, 'urlopen', return_value=response(payload)):
            found = google.search_images('cat', 'fake')
        self.assertEqual([c['url'] for c in found], ['https://example.org/wide.jpg', 'https://example.org/portrait.jpg'])

    def test_perfect_aspect_ratio_must_not_promote_low_google_rank_unrelated_images(self):
        rows = [{'original': f'https://example.org/food-{i}.jpg', 'title': 'Chân gà sả tắc',
                 'original_width': 900, 'original_height': 600, 'position': i + 1} for i in range(8)]
        rows.extend({'original': f'https://example.org/house-{i}.jpg', 'title': 'House design',
                     'original_width': 800, 'original_height': 600, 'position': i + 9} for i in range(20))
        with patch.object(google, 'urlopen', return_value=response({'images_results': rows})):
            candidates = google.search_images('chân gà sả tắc đĩa trắng', 'fake')
        self.assertEqual(len(candidates), 8)
        self.assertTrue(all('/food-' in c['url'] for c in candidates))

    def test_search_retries_reuse_candidates_without_spending_another_search(self):
        with patch.object(google, 'urlopen', return_value=response({'images_results': []})) as send:
            google.search_images('cat orange', 'fake')
            google.search_images('cat orange', 'fake')
            google.search_images('cat black', 'fake')
        self.assertEqual(send.call_count, 2)

    def test_http_errors_and_json_errors_do_not_leak_key(self):
        for code in (401, 403, 429, 500):
            with self.subTest(code=code), patch.object(google, 'urlopen', side_effect=HTTPError(
                    'https://serpapi.com/search?api_key=SUPERSECRET', code, 'SUPERSECRET', {}, io.BytesIO())):
                with self.assertRaisesRegex(google.GoogleImageSearchError, f'HTTP_{code}') as caught:
                    google.search_images('cat', 'SUPERSECRET')
                self.assertNotIn('SUPERSECRET', str(caught.exception))
        with patch.object(google, 'urlopen', return_value=response({'error': 'SUPERSECRET rejected'})):
            with self.assertRaises(google.GoogleImageSearchError) as caught:
                google.search_images('cat', 'SUPERSECRET')
            self.assertNotIn('SUPERSECRET', str(caught.exception))

    def test_overlarge_response_is_rejected(self):
        result = MagicMock()
        result.__enter__.return_value.read.return_value = b' ' * (google.MAX_RESPONSE_BYTES + 1)
        with patch.object(google, 'urlopen', return_value=result):
            with self.assertRaises(google.GoogleImageSearchError):
                google.search_images('cat', 'fake')

    def test_network_diagnostics_distinguish_causes_without_exposing_credentials(self):
        for error, code in (
                (TimeoutError('SUPERSECRET'), 'TIMEOUT'),
                (URLError(socket.gaierror(-2, 'SUPERSECRET')), 'DNS_FAILURE'),
                (URLError(ssl.SSLError('SUPERSECRET')), 'TLS_FAILURE'),
                (URLError(ConnectionRefusedError('SUPERSECRET')), 'CONNECTION_REFUSED'),
                (URLError('https://serpapi.com/?api_key=SUPERSECRET'), 'NETWORK_ERROR')):
            with self.subTest(code=code), patch.object(google, 'urlopen', side_effect=error):
                with self.assertRaises(google.GoogleImageSearchError) as caught:
                    google.search_images('cat', 'SUPERSECRET')
                self.assertIn('reason=' + code, str(caught.exception))
                self.assertNotIn('SUPERSECRET', str(caught.exception))


class PixelSelectionTest(unittest.TestCase):
    def setUp(self):
        images.clear_verification_backoff()
        self.enterContext(patch.object(google, 'get_api_key', return_value=''))
        self.enterContext(patch.dict(os.environ, {'WISIO_IMAGE_SOURCE': 'auto'}))

    def test_search_extracts_dish_from_conversation_instead_of_sending_whole_sentence(self):
        query = images.google_search_query(
            'Hôm nay tôi muốn ăn một món ngon. Bạn có thể cho mình xem hình chân gà xào sả ớt trên đĩa trắng được không?',
            'chan ga xao sa ot')
        self.assertEqual(query, 'chân gà xào sả ớt trên đĩa trắng')

    def test_search_extracts_animal_and_preserves_all_visual_details(self):
        query = images.google_search_query(
            'Tôi đang học về động vật. Cho tôi xem hai con mèo màu cam đang ngủ trên ghế sofa, ảnh chụp nhé.', 'cat')
        self.assertEqual(query, 'hai con mèo màu cam đang ngủ trên ghế sofa, ảnh chụp')

    def test_search_uses_relevant_scene_without_duplicating_generic_subject(self):
        query = images.google_search_query(
            'chicken; user scene: Tôi muốn xem chân gà sả tắc trong tô trắng được không?', 'chan ga sa tac')
        self.assertEqual(query, 'chân gà sả tắc trong tô trắng')

    def test_search_keeps_uncommon_visual_traits(self):
        query = images.google_search_query(
            'Giúp mình tìm hình con mèo tam thể đeo khăn quàng đỏ bên cạnh bình hoa nhé', 'cat')
        self.assertEqual(query, 'con mèo tam thể đeo khăn quàng đỏ bên cạnh bình hoa')

    def test_search_strips_english_dialogue_without_losing_count_color_or_scene(self):
        query = images.google_search_query(
            'I am learning animals today. Could you show me three orange cats playing in a garden cartoon please?', 'cat')
        self.assertEqual(query, 'three orange cats playing in a garden cartoon')

    def test_category_lesson_context_is_not_sent_as_an_image_search(self):
        query = images.google_search_query(
            'orange cat cartoon; user scene: Dạy cho mình 20 từ vựng động vật, kiểu hoạt hình nhé', 'cat')
        self.assertEqual(query, 'orange cat cartoon')

    def test_list_scene_does_not_mix_other_dishes_into_an_animal_search(self):
        self.assertEqual(images.google_search_query(
            'orange cat cartoon; user scene: Dạy các từ con mèo và chân gà', 'cat'),
            'orange cat cartoon')

    def test_polite_endings_must_not_remove_a_house_subject_or_illustration_style(self):
        self.assertEqual(images.google_search_query('Cho mình xem ngôi nhà', 'house'), 'ngôi nhà')
        self.assertEqual(images.google_search_query('minh hoa con meo', 'cat'), 'minh hoa con meo')
        self.assertEqual(images.google_search_query('Cho xem con mèo đang ngủ trong nhà', 'cat'),
                         'con mèo đang ngủ trong nhà')

    def test_search_extracts_known_english_plural_subjects(self):
        self.assertEqual(images.google_search_query('Could you show me two butterflies please?', 'butterfly'),
                         'two butterflies')

    def test_503_switches_model_once_reusing_same_pixels_and_backs_off_failed_model(self):
        good = response(verdict_payload(dict.fromkeys(FIELDS, True)))
        with patch.dict(os.environ, {'WISIO_IMAGE_VERIFY_MODEL': 'gemini-3.8-flash',
                                     'WISIO_IMAGE_VERIFY_FALLBACK_MODEL': 'gemini-3.1-flash-lite'}), \
             patch.object(images, 'urlopen', side_effect=[
                 HTTPError('https://api/', 503, 'overloaded', {}, io.BytesIO()), good, good]) as send:
            images.verify_image_subject(b'same pixels', 'orange cat', 'cat', 'fake')
            images.verify_image_subject(b'same pixels', 'orange cat', 'cat', 'fake')
        urls = [call.args[0].full_url for call in send.call_args_list]
        self.assertEqual(len(urls), 3)
        self.assertIn('gemini-3.8-flash:', urls[0])
        self.assertTrue(all('gemini-3.1-flash-lite:' in url for url in urls[1:]))
        bodies = [json.loads(call.args[0].data) for call in send.call_args_list]
        self.assertEqual(bodies[0]['contents'], bodies[1]['contents'])
        self.assertEqual(bodies[1]['generationConfig']['thinkingConfig']['thinkingLevel'], 'minimal')

    def test_default_vision_model_is_38_flash_with_supported_low_thinking(self):
        with patch.dict(os.environ, {'WISIO_IMAGE_VERIFY_MODEL': ''}), \
             patch.object(images, 'urlopen', return_value=response(verdict_payload(dict.fromkeys(FIELDS, True)))) as send:
            images.verify_image_subject(b'pixels', 'orange cat', 'cat', 'fake')
        self.assertIn('gemini-3.8-flash:', send.call_args.args[0].full_url)
        body = json.loads(send.call_args.args[0].data)
        self.assertEqual(body['generationConfig']['thinkingConfig']['thinkingLevel'], 'low')

    def test_squid_cake_keeps_dish_and_region_instead_of_searching_english_sentence(self):
        self.assertEqual(images.google_search_query(
            'fried squid cake from Quang Ninh Vietnam', 'cha muc'),
            'chả mực from Quảng Ninh Vietnam')
        self.assertEqual(images.vietnamese_dish('chả mực'),
                         ('cha muc', 'Vietnamese fried squid cake'))

    def test_google_query_removes_dialogue_and_restores_vietnamese_dish_and_plate(self):
        query = images.google_search_query('toi muon xem chan ga sa tac trong dia trang photo', 'chan ga sa tac')
        self.assertIn('chân gà sả tắc', query)
        self.assertIn('đĩa trắng', query)
        self.assertNotIn('toi muon xem', query)

    def test_google_query_preserves_english_shape_and_other_attributes(self):
        self.assertEqual(images.google_search_query('U shaped magnet illustration', 'magnet'),
                         'U shaped magnet illustration')
        self.assertEqual(images.google_search_query('robot dog illustration', 'robot dog'),
                         'robot dog illustration')
        self.assertEqual(images.google_search_query('three orange cats playing in a garden cartoon', 'cat'),
                         'three orange cats playing in a garden cartoon')
        self.assertIn('đĩa màu xanh có viền vàng', images.google_search_query(
            'Wisio, tôi muốn xem chân gà sả tắc trong đĩa màu xanh có viền vàng photo', 'chan ga sa tac'))

    def test_rejection_reports_each_failed_criterion(self):
        verdicts = {'images': [{'id': 0, **dict.fromkeys(FIELDS, True), 'matches_attributes': False}]}
        with patch.object(images, 'urlopen', return_value=response(verdict_payload(verdicts))):
            self.assertEqual(images.verify_image_candidates([b'actual pixels'], 'chân gà sả tắc đĩa trắng', 'chan ga sa tac', 'fake'), [])
        self.assertEqual(images._IMAGE_OPERATION.batch_verdicts[0]['failed_checks'], ['matches_attributes'])

    def test_google_pipeline_searches_native_scene_and_verifies_full_request(self):
        from PIL import Image
        original = Image.new('RGB', (320, 240), 'white')
        buffer = io.BytesIO()
        original.save(buffer, format='PNG')
        query = 'Hôm nay tôi đang đói. Bạn có thể cho tôi xem hình chân gà sả tắc trong đĩa trắng photo được không?'
        candidate = {'url': 'https://example.org/dish.jpg', 'title': 'dish', 'google_position': 1}
        verdicts = {'images': [{'id': 0, **dict.fromkeys(FIELDS, True)}]}
        with patch.object(google, 'search_images', return_value=[candidate]) as search, \
             patch.object(images, '_read_url', return_value=buffer.getvalue()), \
             patch.object(images, 'urlopen', return_value=response(verdict_payload(verdicts))) as vision:
            result = images._prepare_google_learning_image(query, 'fake-gemini', 'chan ga sa tac', 'fake-serpapi')
        self.assertEqual(search.call_args.args[0], 'chân gà sả tắc trong đĩa trắng photo')
        self.assertTrue(result['verified'])
        prompt = json.loads(vision.call_args.args[0].data)['contents'][0]['parts'][0]['text']
        self.assertIn(query, prompt)
        self.assertIn('Vietnamese chicken feet with lemongrass and kumquat', prompt)
        self.assertEqual(Image.open(io.BytesIO(result['png'])).size, (320, 240))

    def test_google_pipeline_reports_rejection_cause_and_candidate_identity(self):
        candidate = {'url': 'https://example.org/dish.jpg', 'title': 'Dish on brown plate', 'google_position': 2}
        verdicts = {'images': [{'id': 0, **dict.fromkeys(FIELDS, True), 'matches_attributes': False}]}
        with patch.object(google, 'search_images', return_value=[candidate]), \
             patch.object(images, '_download_google_candidate', return_value=(candidate, b'pixels')), \
             patch.object(images, 'urlopen', return_value=response(verdict_payload(verdicts))), \
             patch('builtins.print') as log:
            with self.assertRaisesRegex(images.LearningImageError, 'GOOGLE_NO_VERIFIED_MATCH'):
                images._prepare_google_learning_image('chân gà sả tắc đĩa trắng', 'fake', 'chan ga sa tac', 'fake')
        lines = [str(call.args[0]) for call in log.call_args_list]
        self.assertTrue(any('Google #2' in line and 'failed=matches_attributes' in line for line in lines))

    def test_learning_photo_preserves_edges_when_fitting_landscape(self):
        from PIL import Image, ImageDraw
        photo = Image.new('RGB', (360, 600), 'blue')
        draw = ImageDraw.Draw(photo)
        draw.rectangle((0, 0, 359, 45), fill='red')
        draw.rectangle((0, 555, 359, 599), fill='green')
        raw = io.BytesIO(); photo.save(raw, format='PNG')
        png = images.make_learning_png(raw.getvalue())
        fitted = Image.open(io.BytesIO(png)).convert('RGB')
        self.assertEqual(fitted.size, (320, 240))
        self.assertGreater(fitted.getpixel((160, 8))[0], 230)
        self.assertGreater(fitted.getpixel((160, 230))[1], 90)


    def test_unauthorized_verifier_does_not_retry_another_model(self):
        with patch.object(images, 'urlopen', side_effect=HTTPError('https://api/', 403, '', {}, io.BytesIO())) as send:
            with self.assertRaisesRegex(images.ImageVerificationUnavailable, 'HTTP_403'):
                images.verify_image_subject(b'pixels', 'cat', 'cat', 'fake')
        send.assert_called_once()

    def test_slow_first_download_does_not_discard_ready_second_candidate(self):
        from concurrent.futures import Future
        slow, ready = Future(), Future()
        candidate = {'url': 'https://example.org/good', 'title': 'orange cat'}
        ready.set_result((candidate, b'correct PNG'))
        with patch.object(google, 'search_images', return_value=[{'url': 'https://example.org/slow'}, candidate]), \
             patch.object(images._IMAGE_DOWNLOAD_POOL, 'submit', side_effect=[slow, ready]), \
             patch.object(images, 'verify_image_candidates', return_value=[0]):
            result = images._prepare_google_learning_image('orange cat', 'gemini', 'cat', 'serpapi')
        self.assertEqual(result['png'], b'correct PNG')
        self.assertTrue(slow.cancelled())

    def test_all_blocked_downloads_are_not_reported_as_wrong_subject(self):
        with patch.object(google, 'search_images', return_value=[{'url': 'https://example.org/blocked', 'title': 'cat'}]), \
             patch.object(images, '_download_google_candidate', return_value=None), \
             patch.object(images, 'verify_image_candidates') as verify:
            with self.assertRaisesRegex(images.LearningImageError, 'GOOGLE_DOWNLOAD_FAILED'):
                images._prepare_google_learning_image('cat', 'gemini', 'cat', 'serpapi')
        verify.assert_not_called()

    def test_original_download_failure_uses_thumbnail_and_still_verifies_pixels(self):
        candidate = {'url': 'https://example.org/original', 'thumbnail': 'https://example.org/thumb'}
        def download(url, *args, **kwargs):
            if url.endswith('original'):
                raise OSError('original blocked')
            return b'thumbnail pixels'
        import time
        with patch.object(images, '_read_url', side_effect=download), \
             patch.object(images, 'make_learning_png', side_effect=lambda b: b + b'-png'):
            prepared = images._download_google_candidate(candidate, time.monotonic() + 5)
        self.assertIsNotNone(prepared)
        self.assertEqual(prepared[1], b'thumbnail pixels-png')
        self.assertEqual(prepared[0]['url'], 'https://example.org/thumb')

    def test_google_cache_never_reuses_an_old_legacy_picture(self):
        with patch.dict(os.environ, {'WISIO_IMAGE_SOURCE': 'auto'}), \
             patch.object(google, 'get_api_key', return_value=''):
            legacy_key = images._image_cache_identity('orange cat', 'cat')[0]
        with patch.dict(os.environ, {'WISIO_IMAGE_SOURCE': 'auto'}), \
             patch.object(google, 'get_api_key', return_value='fake'):
            google_key = images._image_cache_identity('orange cat', 'cat')[0]
        self.assertNotEqual(legacy_key, google_key)

    def test_single_verdict_ignores_thought_and_key_is_header_only(self):
        with patch.object(images, 'urlopen', return_value=response(verdict_payload(dict.fromkeys(FIELDS, True)))) as send:
            images.verify_image_subject(b'actual pixels', 'orange cat photo', 'cat', 'SECRET')
        request = send.call_args.args[0]
        self.assertNotIn('SECRET', request.full_url)
        body = json.loads(request.data)
        self.assertGreaterEqual(body['generationConfig']['maxOutputTokens'], 1024)
        self.assertEqual(body['generationConfig']['thinkingConfig']['thinkingLevel'], 'low')

    def test_http_and_truncation_are_diagnosable_without_key(self):
        with patch.object(images, 'urlopen', side_effect=HTTPError('https://api/?key=SECRET', 429, 'SECRET', {}, io.BytesIO())):
            with self.assertRaisesRegex(images.ImageVerificationUnavailable, 'HTTP_429') as caught:
                images.verify_image_subject(b'pixels', 'cat', 'cat', 'SECRET')
            self.assertNotIn('SECRET', str(caught.exception))
        with patch.object(images, 'urlopen', return_value=response(verdict_payload({}, 'MAX_TOKENS'))):
            with self.assertRaisesRegex(images.ImageVerificationUnavailable, 'MAX_TOKENS'):
                images.verify_image_subject(b'pixels', 'cat', 'cat', 'SECRET')

    def test_batch_checks_each_final_png_and_rejects_wrong_color(self):
        verdicts = {'images': [
            {'id': 0, **dict.fromkeys(FIELDS, True), 'matches_attributes': False},
            {'id': 1, **dict.fromkeys(FIELDS, True)}]}
        with patch.object(images, 'urlopen', return_value=response(verdict_payload(verdicts))) as send:
            approved = images.verify_image_candidates([b'black cat pixels', b'orange cat pixels'], 'orange cat photo', 'cat', 'fake')
        self.assertEqual(approved, [1])
        parts = json.loads(send.call_args.args[0].data)['contents'][0]['parts']
        pixels = [base64.b64decode(p['inlineData']['data']) for p in parts if 'inlineData' in p]
        self.assertEqual(pixels, [b'black cat pixels', b'orange cat pixels'])

    def test_duplicate_out_of_range_and_missing_batch_ids_fail_closed(self):
        good = dict.fromkeys(FIELDS, True)
        for rows in ([{'id': 0, **good}, {'id': 0, **good}],
                     [{'id': 3, **good}], [{'id': 0, **good}]):
            with self.subTest(rows=rows), patch.object(images, 'urlopen', return_value=response(verdict_payload({'images': rows}))):
                with self.assertRaises(images.ImageVerificationUnavailable):
                    images.verify_image_candidates([b'first', b'second'], 'cat', 'cat', 'fake')

    def test_google_pipeline_skips_broken_download_and_selects_verified_png(self):
        candidates = [{'url': 'https://example.org/broken', 'title': 'broken'},
                      {'url': 'https://example.org/black', 'title': 'black'},
                      {'url': 'https://example.org/orange', 'title': 'orange', 'page_url': 'https://example.org/cat'}]
        def download(url, *args, **kwargs):
            if url.endswith('broken'):
                raise OSError('broken')
            return url.rsplit('/', 1)[-1].encode()
        with patch.object(google, 'get_api_key', return_value='fake'), \
             patch.object(google, 'search_images', return_value=candidates), \
             patch.object(images, '_read_url', side_effect=download), \
             patch.object(images, 'make_learning_png', side_effect=lambda b: b + b'-png'), \
             patch.object(images, 'verify_image_candidates', side_effect=lambda pngs, *_: [
                 index for index, png in enumerate(pngs) if png == b'orange-png']), \
             patch.object(images, 'find_thumbnails') as legacy:
            result = images._prepare_uncached_learning_image('orange cat photo', 'fake-gemini', 'cat')
        self.assertEqual(result['png'], b'orange-png')
        self.assertEqual(result['source_provider'], 'Google Images / SerpApi')
        self.assertTrue(result['verified'])
        legacy.assert_not_called()

    def test_explicit_google_without_key_does_not_silently_use_old_sources(self):
        with patch.dict(os.environ, {'WISIO_IMAGE_SOURCE': 'google'}), \
             patch.object(google, 'get_api_key', return_value=''), \
             patch.object(images, 'find_thumbnails') as legacy:
            with self.assertRaisesRegex(images.LearningImageError, 'SERPAPI_KEY_MISSING'):
                images._prepare_uncached_learning_image('cat', 'gemini', 'cat')
            legacy.assert_not_called()


class PrivateConfigTest(unittest.TestCase):
    def test_configuration_validates_before_saving(self):
        import configure_google_images as config
        with patch.object(config.getpass, 'getpass', return_value='fake'), \
             patch.object(google, 'search_images', side_effect=google.GoogleImageSearchError('HTTP_401')), \
             patch.object(google, 'save_api_key') as save:
            self.assertEqual(config.main(), 1)
        save.assert_not_called()

    def test_windows_encrypted_key_roundtrip_not_plaintext(self):
        if os.name != 'nt':
            self.skipTest('Windows DPAPI only')
        folder = Path(__file__).with_name('test-tmp') / ('google-key-' + uuid.uuid4().hex)
        folder.mkdir(parents=True)
        try:
            path = folder / '.wisio_serpapi_secret'
            google.save_api_key('fake-test-secret-123', path)
            self.assertNotIn(b'fake-test-secret-123', path.read_bytes())
            with patch.dict(os.environ, {'SERPAPI_API_KEY': ''}):
                self.assertEqual(google.get_api_key(path), 'fake-test-secret-123')
                path.write_bytes(b'broken ciphertext')
                with self.assertRaises(google.GoogleImageSearchError):
                    google.get_api_key(path)
        finally:
            shutil.rmtree(folder)

    def test_environment_key_overrides_private_file(self):
        with patch.dict(os.environ, {'SERPAPI_API_KEY': 'fake-env'}):
            self.assertEqual(google.get_api_key(Path('nonexistent')), 'fake-env')


if __name__ == '__main__':
    unittest.main()
