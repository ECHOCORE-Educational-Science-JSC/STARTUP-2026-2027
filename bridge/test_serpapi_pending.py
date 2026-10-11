"""A cold Google search may take more than eight seconds; retrieve the same job."""
import json
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch

import google_image_search as google


def response(payload):
    result = MagicMock()
    result.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return result


class PendingSearchTest(unittest.TestCase):
    def setUp(self):
        google.clear_search_cache()
        self.now = 0.0
        self.enterContext(patch.object(google.time, 'monotonic', side_effect=lambda: self.now))
        self.enterContext(patch.object(google.time, 'sleep', side_effect=self.advance))

    def advance(self, seconds):
        self.now += seconds

    def test_processing_for_eleven_seconds_is_not_a_network_error_or_empty_cache(self):
        job_id = 'a' * 24
        def upstream(request, timeout):
            parsed = urlsplit(request.full_url)
            if parsed.path == '/search.json':
                self.assertEqual(parse_qs(parsed.query)['async'], ['true'])
                return response({'search_metadata': {'id': job_id, 'status': 'Processing'}})
            self.assertEqual(parsed.path, f'/searches/{job_id}.json')
            if self.now < 11:
                return response({'search_metadata': {'id': job_id, 'status': 'Processing'}})
            return response({'search_metadata': {'id': job_id, 'status': 'Success'},
                             'images_results': [{'original': 'https://example.org/squid.jpg'}]})
        with patch.object(google, 'urlopen', side_effect=upstream) as send:
            result = google.search_images('chả mực', 'fake', timeout=18)
            cached = google.search_images('chả mực', 'fake', timeout=18)
        self.assertEqual(result[0]['url'], 'https://example.org/squid.jpg')
        self.assertEqual(cached, result)
        self.assertGreaterEqual(self.now, 11)
        self.assertEqual(sum(urlsplit(c.args[0].full_url).path == '/search.json'
                             for c in send.call_args_list), 1)

    def test_pending_job_exhausts_total_budget_without_starting_a_second_search(self):
        pending = response({'search_metadata': {'id': 'b' * 24, 'status': 'Queued'}})
        with patch.object(google, 'urlopen', return_value=pending) as send:
            with self.assertRaisesRegex(google.GoogleImageSearchError, 'PROCESSING_TIMEOUT'):
                google.search_images('cat', 'SUPERSECRET', timeout=2)
        self.assertLessEqual(self.now, 2)
        self.assertEqual(sum(urlsplit(c.args[0].full_url).path == '/search.json'
                             for c in send.call_args_list), 1)

    def test_upstream_job_id_cannot_redirect_private_key_to_another_host(self):
        for job_id in ('https://evil.example/SUPERSECRET', '../secret', '', None):
            with self.subTest(job_id=job_id), patch.object(google, 'urlopen', return_value=response({
                    'search_metadata': {'status': 'Processing', 'id': job_id}})) as send:
                with self.assertRaisesRegex(google.GoogleImageSearchError, 'MALFORMED') as caught:
                    google.search_images('cat', 'SUPERSECRET', timeout=2)
                self.assertNotIn('SUPERSECRET', str(caught.exception))
                self.assertEqual(send.call_count, 1)

    def test_provider_error_state_is_not_cached_as_no_images(self):
        with patch.object(google, 'urlopen', return_value=response({
                'search_metadata': {'status': 'Error'}})):
            with self.assertRaisesRegex(google.GoogleImageSearchError, 'API_ERROR'):
                google.search_images('cat', 'fake')

    def test_success_for_another_search_is_rejected(self):
        with patch.object(google, 'urlopen', side_effect=[
                response({'search_metadata': {'id': 'a' * 24, 'status': 'Processing'}}),
                response({'search_metadata': {'id': 'b' * 24, 'status': 'Success'}, 'images_results': []})]):
            with self.assertRaisesRegex(google.GoogleImageSearchError, 'MALFORMED'):
                google.search_images('cat', 'fake')

    def test_one_archive_read_timeout_can_recover_without_resubmitting_search(self):
        completed = response({'search_metadata': {'id': 'c' * 24, 'status': 'Success'},
                              'images_results': [{'original': 'https://example.org/cat.png'}]})
        with patch.object(google, 'urlopen', side_effect=[
                response({'search_metadata': {'id': 'c' * 24, 'status': 'Processing'}}),
                TimeoutError('SUPERSECRET'), completed]) as send:
            found = google.search_images('cat', 'SUPERSECRET')
        self.assertEqual(len(found), 1)
        self.assertEqual(send.call_count, 3)
        self.assertTrue(all('/searches/' in c.args[0].full_url for c in send.call_args_list[1:]))


if __name__ == '__main__':
    unittest.main()
