"""Deterministic cold-path scheduling tests; no image provider is contacted."""
import base64
from concurrent.futures import Future, TimeoutError
import io
import json
import unittest
from unittest.mock import patch

from PIL import Image
import learning_image as images


FIELDS = ('matches_subject', 'matches_attributes', 'matches_image_type',
          'suitable_for_child', 'landscape_fit', 'subject_fully_visible')


class SimulatedClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


class ScheduledDownload(Future):
    """A downloader's completion time, independent of foreground wait order."""
    def __init__(self, clock, ready_at, value):
        super().__init__()
        self.clock, self.ready_at, self.value = clock, ready_at, value

    def done(self):
        if not super().done() and self.clock.now >= self.ready_at:
            self.set_result(self.value)
        return super().done()

    def result(self, timeout=None):
        if not self.done():
            if timeout is not None and self.ready_at > self.clock.now + timeout:
                self.clock.now += timeout
                raise TimeoutError()
            self.clock.now = self.ready_at
            self.done()
        return super().result(timeout=0)


class ScheduledDownloads:
    def __init__(self, clock, candidates, delays, pngs):
        self.clock, self.delays, self.pngs = clock, delays, pngs
        self.positions = {candidate['url']: index for index, candidate in enumerate(candidates)}
        self.futures = []

    def submit(self, _downloader, candidate, _deadline):
        index = self.positions[candidate['url']]
        future = ScheduledDownload(self.clock, self.clock.now + self.delays[index],
                                   (candidate, self.pngs[index]))
        self.futures.append(future)
        return future

    def wait(self, futures, timeout=None, return_when=None):
        done = {future for future in futures if future.done()}
        if not done:
            next_time = min(future.ready_at for future in futures)
            self.clock.now = min(next_time, self.clock.now + timeout) if timeout is not None else next_time
            done = {future for future in futures if future.done()}
        return done, set(futures) - done


def png(color):
    data = io.BytesIO()
    Image.new('RGB', (320, 240), color).save(data, format='PNG')
    return data.getvalue()


class ColdImageLatencyTest(unittest.TestCase):
    def setUp(self):
        images.clear_verification_backoff()
        self.clock = SimulatedClock()
        self.enterContext(patch.object(images.time, 'monotonic', self.clock.monotonic))
        self.addCleanup(lambda: images._IMAGE_OPERATION.__dict__.clear())

    def prepare(self, delays, good_index, budget=16, checks=None):
        candidates = [{'url': f'https://images.example/{index}.png',
                       'title': f'Tea candidate {index}', 'google_position': index + 1}
                      for index in range(len(delays))]
        pngs = [png((index * 23 % 255, 120, 60)) for index in range(len(delays))]
        pool = ScheduledDownloads(self.clock, candidates, delays, pngs)
        verified_pixels = []

        def vision(request, **_kwargs):
            self.clock.now += .8
            parts = json.loads(request.data)['contents'][0]['parts']
            pixels = [base64.b64decode(part['inlineData']['data'])
                      for part in parts if 'inlineData' in part]
            verified_pixels.extend(pixels)
            rows = []
            for index, pixels_png in enumerate(pixels):
                fields = dict.fromkeys(FIELDS, True)
                if good_index is None or pixels_png != pngs[good_index]:
                    fields['matches_subject'] = False
                if checks:
                    fields.update(checks)
                rows.append({'id': index, **fields})
            payload = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
                {'text': json.dumps({'images': rows})}]}}]}
            response = io.BytesIO(json.dumps(payload).encode())
            return response

        images._IMAGE_OPERATION.deadline = budget
        with patch.object(images.google_image_search, 'search_images', return_value=candidates), \
             patch.object(images, '_IMAGE_DOWNLOAD_POOL', pool), \
             patch.object(images, 'wait', pool.wait, create=True), \
             patch.object(images, 'urlopen', side_effect=vision):
            result = images._prepare_google_learning_image('trà photo', 'fake-gemini', 'tea', 'fake-serpapi')
        self.assertEqual(result['png'], pngs[good_index])
        self.assertIs(result['verified'], True)
        self.assertIn(result['png'], verified_pixels)
        return result, pool, verified_pixels

    def test_fast_verified_candidate_does_not_wait_for_other_hosts(self):
        # Waiting all first-batch downloads delays a .1s candidate until 2s.
        result, pool, _ = self.prepare([2, .1, 2, 2], good_index=1)
        self.assertLessEqual(self.clock.now, 1.0)
        self.assertEqual(result['source_url'], 'https://images.example/1.png')
        self.assertTrue(all(future.done() for future in pool.futures))
        print(f'[SIMULATED IMAGE LATENCY] first-ready tea: {self.clock.now:.2f}s; old batch barrier 2.80s')

    def test_second_group_starts_before_first_group_verification(self):
        # Serial four-download batches hide the only correct, already-fast host.
        result, _, _ = self.prepare([2, 2, 2, 2, .1, 2, 2, 2], good_index=4)
        self.assertLessEqual(self.clock.now, 1.0)
        self.assertEqual(result['source_url'], 'https://images.example/4.png')

    def test_fast_wrong_image_is_rejected_then_ready_correct_pixels_are_verified(self):
        result, _, verified = self.prepare([.1, 1.2, 3, 3], good_index=1)
        self.assertEqual(result['source_url'], 'https://images.example/1.png')
        self.assertGreaterEqual(len(verified), 2)
        self.assertLessEqual(self.clock.now, 2.1)

    def test_each_of_six_checks_still_rejects_fast_image(self):
        for field in FIELDS:
            with self.subTest(field=field):
                self.clock.now = 0
                with self.assertRaisesRegex(images.LearningImageError, 'GOOGLE_NO_VERIFIED_MATCH'):
                    self.prepare([.1], good_index=0, checks={field: False})

    def test_download_budget_expires_before_verification_and_cancels_unused_work(self):
        # A pending host may exceed the lesson budget, but it cannot start vision.
        with self.assertRaisesRegex(images.LearningImageError, 'hết thời gian'):
            self.prepare([30, 30], good_index=0, budget=1)
        self.assertLessEqual(self.clock.now, 1)


if __name__ == '__main__':
    unittest.main()
