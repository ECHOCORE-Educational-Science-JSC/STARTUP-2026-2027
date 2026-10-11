"""Vision outage recovery must use the same pixels and preserve negative verdicts."""
import json
import io
import os
import random
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import learning_image as images


GOOD = dict.fromkeys(images._VERDICT_FIELDS, True)


class VisionRecoveryTest(unittest.TestCase):
    def setUp(self):
        images.clear_verification_backoff()
        self.enterContext(patch.dict(os.environ, {'WISIO_IMAGE_VERIFY_MODEL': 'gemini-3.8-flash',
                                                 'WISIO_IMAGE_VERIFY_FALLBACK_MODEL': 'gemini-3.5-flash-lite'}))

    def test_slow_primary_is_not_allowed_to_hold_a_ready_fallback(self):
        release, finished, fallback_started = threading.Event(), threading.Event(), threading.Event()
        parts = [{'text': 'same constraints'}, images._png_part(b'same final pixels')]
        calls = []
        def attempt(received, key, batch, model):
            calls.append((model, received))
            if model == 'gemini-3.8-flash':
                try:
                    if not release.wait(1):
                        raise images._verification_failure('TIMEOUT_OR_NETWORK', model)
                    return dict(GOOD)
                finally:
                    finished.set()
            fallback_started.set()
            return dict(GOOD)
        with patch.object(images, '_request_pixel_verdict_once', side_effect=attempt), \
             patch.object(images, 'VISION_HEDGE_SECONDS', .02, create=True):
            try:
                result = images._request_pixel_verdict(parts, 'fake')
                self.assertTrue(fallback_started.is_set(), 'Fallback must begin while the primary is still pending')
                self.assertFalse(finished.is_set(), 'Do not wait for the primary timeout before launching fallback')
                self.assertFalse(release.is_set())
                self.assertEqual(result, GOOD)
            finally:
                release.set()
                finished.wait(1)
        self.assertTrue(all(received == parts for _, received in calls))

    def test_negative_primary_is_not_retried_until_a_model_agrees(self):
        bad = {**GOOD, 'matches_subject': False}
        with patch.object(images, '_request_pixel_verdict_once', return_value=bad) as send:
            with self.assertRaises(images.LearningImageError):
                images.verify_image_subject(b'wrong pixels', 'chả mực', 'cha muc', 'fake')
        self.assertEqual(send.call_count, 1)

    def test_expired_parent_deadline_does_not_start_calls_or_blacklist_models(self):
        images._IMAGE_OPERATION.deadline = time.monotonic() - 1
        try:
            with patch.object(images, '_request_pixel_verdict_once') as send:
                with self.assertRaises(images.LearningImageError):
                    images._request_pixel_verdict([], 'fake')
                send.assert_not_called()
            self.assertEqual(images._VERIFY_BACKOFF, {})
        finally:
            del images._IMAGE_OPERATION.deadline

    def test_default_fallback_has_current_flash_lite_with_eight_second_attempt_budget(self):
        with patch.dict(os.environ, {'WISIO_IMAGE_VERIFY_FALLBACK_MODEL': ''}):
            self.assertEqual(images.DEFAULT_IMAGE_VERIFY_FALLBACK_MODEL, 'gemini-3.5-flash-lite')
        reply = MagicMock()
        reply.__enter__.return_value.read.return_value = json.dumps({'candidates': [{
            'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(GOOD)}]}}]}).encode()
        with patch.object(images, 'urlopen', return_value=reply) as send:
            images._request_pixel_verdict_once([], 'fake', False, 'gemini-3.5-flash-lite')
        self.assertEqual(send.call_args.kwargs['timeout'], 8)

    def test_squid_paste_alias_keeps_region_color_slicing_and_plate(self):
        self.assertEqual(images.google_search_query(
            'Fried squid paste cake, Ha Long style, golden brown, sliced on a plate', 'cha muc'),
            'chả mực, Hạ Long style, golden brown, sliced on a plate')

    def test_fallback_rejection_wins_while_primary_is_still_pending(self):
        release, finished = threading.Event(), threading.Event()
        def attempt(parts, key, batch, model):
            if model == 'gemini-3.8-flash':
                try:
                    release.wait(1)
                    return dict(GOOD)
                finally: finished.set()
            return {**GOOD, 'matches_attributes': False}
        with patch.object(images, '_request_pixel_verdict_once', side_effect=attempt), \
             patch.object(images, 'VISION_HEDGE_SECONDS', .02):
            try:
                with self.assertRaises(images.LearningImageError):
                    images.verify_image_subject(b'raw squid', 'chả mực, sliced', 'cha muc', 'fake')
                self.assertFalse(finished.is_set())
            finally:
                release.set()
                finished.wait(1)

    def test_total_vision_budget_does_not_add_both_model_timeouts(self):
        release = threading.Event()
        finished = [threading.Event(), threading.Event()]
        def attempt(parts, key, batch, model):
            try:
                release.wait(1)
                return dict(GOOD)
            finally: finished[model != 'gemini-3.8-flash'].set()
        with patch.object(images, '_request_pixel_verdict_once', side_effect=attempt), \
             patch.object(images, 'VISION_HEDGE_SECONDS', .01), \
             patch.object(images, 'VISION_BUDGET_SECONDS', .05):
            try:
                with self.assertRaisesRegex(images.ImageVerificationUnavailable, 'DEADLINE_EXCEEDED'):
                    images._request_pixel_verdict([], 'fake')
                self.assertEqual(images._VERIFY_BACKOFF, {})
            finally:
                release.set()
                for done in finished: done.wait(1)

    def test_large_photo_becomes_smaller_png_before_exact_pixels_are_verified(self):
        from PIL import Image
        rng = random.Random(17)
        photo = Image.new('RGB', (320, 240))
        photo.putdata([(
            min(255, max(0, x * 255 // 320 + rng.randrange(-8, 9))),
            min(255, max(0, y * 255 // 240 + rng.randrange(-8, 9))),
            min(255, max(0, (x + y) * 255 // 560 + rng.randrange(-8, 9))))
            for y in range(240) for x in range(320)])
        source = io.BytesIO()
        photo.save(source, format='PNG')
        png = images.make_learning_png(source.getvalue())
        self.assertLess(len(png), 64 * 1024)
        self.assertTrue(images._valid_cached_png(png))
        final = Image.open(io.BytesIO(png))
        self.assertEqual(final.size, (320, 240))
        self.assertEqual(final.mode, 'P')
        reply = MagicMock()
        reply.__enter__.return_value.read.return_value = json.dumps({'candidates': [{
            'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(GOOD)}]}}]}).encode()
        with patch.object(images, 'urlopen', return_value=reply) as send:
            images.verify_image_subject(png, 'photo', 'photo', 'fake')
        # The verifier sees the exact indexed PNG later sent to the robot.
        self.assertEqual(json.loads(send.call_args.args[0].data)['contents'][0]['parts'][1],
                         images._png_part(png))


if __name__ == '__main__':
    unittest.main()
