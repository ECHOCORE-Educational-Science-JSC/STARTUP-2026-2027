"""Verified vocabulary images survive restarts without duplicate downloads."""

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import shutil
import threading
import time
import unittest
from unittest.mock import patch
import uuid

import learning_image
from PIL import Image


class VerifiedImageCacheTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(learning_image.google_image_search, 'get_api_key', return_value=''))
        self.enterContext(patch.dict(learning_image.os.environ, {'WISIO_IMAGE_SOURCE': 'auto'}))
        self.cache_dir = Path(__file__).with_name("test-tmp") / ("image-cache-" + uuid.uuid4().hex)
        self.cache_dir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.cache_dir)
        self.patch_dir = patch.object(
            learning_image, "IMAGE_CACHE_DIR", self.cache_dir, create=True)
        self.patch_dir.start()
        self.addCleanup(self.patch_dir.stop)
        learning_image._IMAGE_CACHE.clear()
        self.addCleanup(learning_image._IMAGE_CACHE.clear)
        image = Image.new("RGB", (640, 480), (80, 120, 160))
        buf = io.BytesIO()
        image.save(buf, format="JPEG")
        self.source = buf.getvalue()

    def prepare(self, query="one orange cat photo", word="cat"):
        with patch.object(learning_image, "find_thumbnails", return_value=[
                ("https://images.example/cat.jpg", "One orange cat photo")]), \
             patch.object(learning_image, "find_openverse_thumbnails", return_value=[]), \
             patch.object(learning_image, "_read_url", return_value=self.source), \
             patch.object(learning_image, "verify_image_subject", return_value=None):
            return learning_image.prepare_learning_image(query, "key", word)

    def disk_record(self):
        files = list(self.cache_dir.glob("*.json"))
        self.assertEqual(len(files), 1, "one successful image should create one disk entry")
        return files[0], json.loads(files[0].read_text(encoding="utf-8"))

    def test_verified_image_is_reused_after_memory_cache_is_cleared(self):
        first = self.prepare()
        learning_image._IMAGE_CACHE.clear()
        with patch.object(learning_image, "_read_url", side_effect=AssertionError("network used")), \
             patch.object(learning_image, "verify_image_subject", side_effect=AssertionError("verified again")):
            second = learning_image.prepare_learning_image("one orange cat photo", "key", "cat")
        self.assertEqual(second["png"], first["png"])
        self.assertIs(second["verified"], True)
        self.assertEqual(second["source_url"], "https://images.example/cat.jpg")

    def test_cache_lookup_does_not_download_on_miss_and_returns_a_copy(self):
        with patch.object(learning_image, "_read_url", side_effect=AssertionError("network used")):
            self.assertIsNone(learning_image.get_cached_learning_image("missing subject", "missing"))
        self.prepare()
        cached = learning_image.get_cached_learning_image("one orange cat photo", "cat")
        self.assertIsNotNone(cached)
        cached["source_title"] = "changed by caller"
        self.assertEqual(learning_image.get_cached_learning_image(
            "one orange cat photo", "cat")["source_title"], "One orange cat photo")

    def test_query_order_qualifiers_and_learning_word_have_distinct_entries(self):
        self.prepare("cat chasing dog", "cat")
        with patch.object(learning_image, "_read_url", side_effect=AssertionError("network used")):
            for query, word in [("dog chasing cat", "cat"), ("black cat chasing dog", "cat"),
                                ("cat chasing dog", "dog"), ("cat chasing dog", "")]:
                with self.subTest(query=query, word=word):
                    self.assertIsNone(learning_image.get_cached_learning_image(query, word))
        self.assertIsNotNone(learning_image.get_cached_learning_image("cat chasing dog", "cat"))

    def test_pixel_verifier_outage_creates_no_cache_entry(self):
        with patch.object(learning_image, "find_thumbnails", return_value=[
                ("https://images.example/cat.jpg", "One orange cat photo")]), \
             patch.object(learning_image, "find_openverse_thumbnails", return_value=[]), \
             patch.object(learning_image, "_read_url", return_value=self.source), \
             patch.object(learning_image, "verify_image_subject", side_effect=
                          learning_image.ImageVerificationUnavailable("verifier offline")):
            with self.assertRaises(learning_image.LearningImageError):
                learning_image.prepare_learning_image("one orange cat photo", "key", "cat")
        self.assertFalse(learning_image._IMAGE_CACHE)
        self.assertEqual(list(self.cache_dir.iterdir()), [])

    def test_mock_or_invalid_png_is_not_persisted(self):
        with patch.object(learning_image, "make_small_png", return_value=b"png"):
            self.prepare()
        self.assertEqual(list(self.cache_dir.iterdir()), [])

    def test_expired_memory_and_disk_entries_are_not_reused(self):
        with patch.object(learning_image, "IMAGE_CACHE_TTL_SECONDS", 5, create=True), \
             patch.object(learning_image.time, "time", return_value=1000):
            self.prepare()
        with patch.object(learning_image, "IMAGE_CACHE_TTL_SECONDS", 5, create=True), \
             patch.object(learning_image.time, "time", return_value=1006):
            self.assertIsNone(learning_image.get_cached_learning_image("one orange cat photo", "cat"))

    def test_unverified_or_old_version_disk_entry_is_ignored(self):
        for field, value in [("verified", False), ("version", 0), ("version", 6), ("verified", "true")]:
            with self.subTest(field=field, value=value):
                self.prepare()
                path, record = self.disk_record()
                record[field] = value
                path.write_text(json.dumps(record), encoding="utf-8")
                learning_image._IMAGE_CACHE.clear()
                self.assertIsNone(learning_image.get_cached_learning_image("one orange cat photo", "cat"))

    def test_mismatched_query_or_word_disk_entry_is_ignored(self):
        for field, value in [("query", "one white cat photo"), ("word", "dog")]:
            with self.subTest(field=field):
                self.prepare()
                path, record = self.disk_record()
                record[field] = value
                path.write_text(json.dumps(record), encoding="utf-8")
                learning_image._IMAGE_CACHE.clear()
                self.assertIsNone(learning_image.get_cached_learning_image("one orange cat photo", "cat"))

    def test_corrupt_verification_timestamp_is_ignored(self):
        self.prepare()
        path, record = self.disk_record()
        record["verified_at"] = 10 ** 1000
        path.write_text(json.dumps(record), encoding="utf-8")
        learning_image._IMAGE_CACHE.clear()
        self.assertIsNone(learning_image.get_cached_learning_image("one orange cat photo", "cat"))

    def test_cache_write_failure_still_returns_the_verified_image(self):
        with patch.object(learning_image.os, "replace", side_effect=PermissionError("cache read-only")):
            result = self.prepare()
        self.assertIs(result["verified"], True)
        self.assertTrue(result["png"].startswith(b"\x89PNG"))
        self.assertEqual(list(self.cache_dir.iterdir()), [])

    def test_legacy_unverified_memory_entry_is_ignored(self):
        self.prepare()
        path, _ = self.disk_record()
        path.unlink()
        for cached in learning_image._IMAGE_CACHE.values():
            cached.pop("verified")
        self.assertIsNone(learning_image.get_cached_learning_image("one orange cat photo", "cat"))

    def test_corrupt_json_png_digest_and_wrong_dimensions_are_ignored(self):
        for corruption in ("json", "png", "digest", "dimensions"):
            with self.subTest(corruption=corruption):
                self.prepare()
                path, record = self.disk_record()
                if corruption == "json":
                    path.write_text("{broken", encoding="utf-8")
                else:
                    if corruption == "png":
                        png = b"\x89PNG\r\n\x1a\ncorrupt"
                    elif corruption == "dimensions":
                        buf = io.BytesIO()
                        Image.new("RGB", (32, 24)).save(buf, format="PNG")
                        png = buf.getvalue()
                    else:
                        png = base64.b64decode(record["png"])
                    record["png"] = base64.b64encode(png).decode("ascii")
                    record["png_sha256"] = ("0" * 64 if corruption == "digest"
                                             else hashlib.sha256(png).hexdigest())
                    path.write_text(json.dumps(record), encoding="utf-8")
                learning_image._IMAGE_CACHE.clear()
                self.assertIsNone(learning_image.get_cached_learning_image("one orange cat photo", "cat"))

    def test_disk_cache_prunes_oldest_entries_to_configured_byte_limit(self):
        with patch.object(learning_image.time, "time", return_value=1000):
            self.prepare("orange cat", "cat")
        first_path, _ = self.disk_record()
        budget = first_path.stat().st_size + 100
        with patch.object(learning_image, "IMAGE_CACHE_MAX_BYTES", budget, create=True), \
             patch.object(learning_image.time, "time", return_value=1001):
            self.prepare("black cat", "cat")
        files = list(self.cache_dir.glob("*.json"))
        self.assertLessEqual(sum(path.stat().st_size for path in files), budget)
        learning_image._IMAGE_CACHE.clear()
        with patch.object(learning_image.time, "time", return_value=1002):
            self.assertIsNone(learning_image.get_cached_learning_image("orange cat", "cat"))
            self.assertIsNotNone(learning_image.get_cached_learning_image("black cat", "cat"))

    def test_parallel_calls_share_one_download_and_verification(self):
        started = threading.Event()
        release = threading.Event()
        calls = []
        calls_lock = threading.Lock()
        barrier = threading.Barrier(5)

        def read(url, *_args):
            with calls_lock:
                calls.append(url)
            started.set()
            if not release.wait(3):
                raise AssertionError("test download was not released")
            return self.source

        def prepare():
            barrier.wait(3)
            return learning_image.prepare_learning_image("one orange cat photo", "key", "cat")

        with patch.object(learning_image, "find_thumbnails", return_value=[
                ("https://images.example/cat.jpg", "One orange cat photo")]), \
             patch.object(learning_image, "_read_url", side_effect=read), \
             patch.object(learning_image, "verify_image_subject", return_value=None) as verify, \
             ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(prepare) for _ in range(4)]
            barrier.wait(3)
            self.assertTrue(started.wait(3))
            time.sleep(0.05)
            release.set()
            results = [future.result(timeout=3) for future in futures]
        self.assertEqual(calls, ["https://images.example/cat.jpg"])
        self.assertEqual(verify.call_count, 1)
        self.assertTrue(all(result == results[0] for result in results))

    def test_single_flight_failure_releases_waiters_and_allows_retry(self):
        started = threading.Event()
        release = threading.Event()
        barrier = threading.Barrier(3)
        calls = []

        def fail_read(url, *_args):
            calls.append(url)
            started.set()
            release.wait(3)
            raise RuntimeError("download crashed")

        def prepare():
            barrier.wait(3)
            return learning_image.prepare_learning_image("one orange cat photo", "key", "cat")

        with patch.object(learning_image, "find_thumbnails", return_value=[
                ("https://images.example/cat.jpg", "One orange cat photo")]), \
             patch.object(learning_image, "_read_url", side_effect=fail_read), \
             ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(prepare) for _ in range(2)]
            barrier.wait(3)
            self.assertTrue(started.wait(3))
            time.sleep(0.05)
            release.set()
            for future in futures:
                with self.assertRaisesRegex(RuntimeError, "download crashed"):
                    future.result(timeout=3)
        self.assertEqual(calls, ["https://images.example/cat.jpg"])
        self.assertIs(self.prepare()["verified"], True)


if __name__ == "__main__":
    unittest.main()
