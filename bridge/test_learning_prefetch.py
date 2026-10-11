import asyncio
import threading
import unittest
from unittest.mock import patch

import learning_image
import learning_prefetch


class PrefetchTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_early_prefetch_is_reported_once_without_starting_search_again(self):
        with patch.object(learning_image, 'get_cached_learning_image', return_value=None), \
             patch.object(learning_image, 'prepare_learning_image', side_effect=
                          learning_image.LearningImageError('SERPAPI_TIMEOUT')) as prepare:
            loader = learning_prefetch.LearningImagePrefetch('key')
            try:
                future = loader._submit('tra tac photo', 'tra tac', 1)
                with self.assertRaises(learning_image.LearningImageError):
                    await asyncio.shield(future)
                with self.assertRaisesRegex(learning_image.LearningImageError, 'SERPAPI_TIMEOUT'):
                    await loader.get('tra tac photo', 'tra tac')
                self.assertEqual(prepare.call_count, 1)
            finally:
                await loader.close()

    async def test_background_failure_logs_diagnostic_code_without_gemini_key(self):
        with patch.object(learning_image, 'prepare_learning_image', side_effect=
                          learning_image.ImageVerificationUnavailable('GEMINI_VERIFY_HTTP_429 secret-key')), \
             patch('builtins.print') as output:
            loader = learning_prefetch.LearningImagePrefetch('secret-key')
            try:
                future = loader._submit('orange cat', 'cat', 1)
                with self.assertRaises(learning_image.ImageVerificationUnavailable):
                    await asyncio.wait_for(asyncio.shield(future), 1)
                log = ' '.join(str(call.args) for call in output.call_args_list)
                self.assertIn('GEMINI_VERIFY_HTTP_429', log)
                self.assertNotIn('secret-key', log)
            finally:
                await loader.close()

    async def test_batch_prepares_concurrently_and_display_reuses_result(self):
        gate = threading.Barrier(3, timeout=2)
        prepared = []

        def prepare(query, key, word):
            prepared.append(word)
            gate.wait()
            return {"png": word.encode(), "verified": True}

        with patch.object(learning_image, "get_cached_learning_image", return_value=None), \
             patch.object(learning_image, "prepare_learning_image", side_effect=prepare):
            loader = learning_prefetch.LearningImagePrefetch("key", workers=3)
            try:
                loader.schedule([{"word": word, "query": word} for word in ("cat", "dog", "bee")])
                images = await asyncio.wait_for(asyncio.gather(*[
                    loader.get(word, word) for word in ("cat", "dog", "bee")]), 3)
                self.assertEqual([image["png"] for image in images], [b"cat", b"dog", b"bee"])
                self.assertEqual((await loader.get("cat", "cat"))["png"], b"cat")
                self.assertEqual(prepared.count("cat"), 1)
            finally:
                await loader.close()

    async def test_different_attributes_never_reuse_old_image(self):
        with patch.object(learning_image, "get_cached_learning_image", return_value=None), \
             patch.object(learning_image, "prepare_learning_image", side_effect=lambda q,k,w: {"png": q.encode(), "verified": True}):
            loader = learning_prefetch.LearningImagePrefetch("key")
            try:
                red = await loader.get("red cat photo", "cat")
                black = await loader.get("black cat photo", "cat")
                self.assertNotEqual(red["png"], black["png"])
            finally:
                await loader.close()

    async def test_foreground_request_has_priority_over_queued_batch(self):
        entered, release = threading.Event(), threading.Event()
        order = []

        def prepare(query, key, word):
            order.append(word)
            if word == "cat":
                entered.set()
                release.wait(2)
            return {"png": word.encode(), "verified": True}

        with patch.object(learning_image, "get_cached_learning_image", return_value=None), \
             patch.object(learning_image, "prepare_learning_image", side_effect=prepare):
            loader = learning_prefetch.LearningImagePrefetch("key", workers=1)
            try:
                loader.schedule([{"word": w, "query": w} for w in ("cat", "dog", "bee")])
                await asyncio.to_thread(entered.wait, 1)
                foreground = asyncio.create_task(loader.get("bee", "bee"))
                await asyncio.sleep(0.02)
                release.set()
                await foreground
                self.assertEqual(order[:2], ["cat", "bee"])
            finally:
                release.set()
                await loader.close()

    async def test_failure_isolated_and_never_displays_unverified_result(self):
        def prepare(query, key, word):
            if word == "cat":
                raise learning_image.LearningImageError("wrong subject")
            return {"png": b"dog", "verified": True}

        with patch.object(learning_image, "get_cached_learning_image", return_value=None), \
             patch.object(learning_image, "prepare_learning_image", side_effect=prepare):
            loader = learning_prefetch.LearningImagePrefetch("key")
            try:
                loader.schedule([{"word": w, "query": w} for w in ("cat", "dog")])
                with self.assertRaises(learning_image.LearningImageError):
                    await loader.get("cat", "cat")
                self.assertEqual((await loader.get("dog", "dog"))["png"], b"dog")
            finally:
                await loader.close()

    async def test_unverified_worker_result_is_rejected(self):
        with patch.object(learning_image, "get_cached_learning_image", return_value=None), \
             patch.object(learning_image, "prepare_learning_image", return_value={"png": b"wrong", "verified": False}):
            loader = learning_prefetch.LearningImagePrefetch("key")
            try:
                with self.assertRaises(learning_image.LearningImageError):
                    await loader.get("orange cat", "cat")
            finally:
                await loader.close()

    async def test_foreground_retries_after_temporary_failure(self):
        with patch.object(learning_image, "get_cached_learning_image", return_value=None), \
             patch.object(learning_image, "prepare_learning_image", side_effect=[
                 learning_image.LearningImageError("temporary outage"), {"png": b"cat", "verified": True}]) as prepare:
            loader = learning_prefetch.LearningImagePrefetch("key")
            try:
                with self.assertRaises(learning_image.LearningImageError):
                    await loader.get("cat", "cat")
                self.assertEqual((await loader.get("cat", "cat"))["png"], b"cat")
                self.assertEqual(prepare.call_count, 2)
            finally:
                await loader.close()

    async def test_new_foreground_displaces_queued_background_when_full(self):
        entered, release = threading.Event(), threading.Event()
        def prepare(query, key, word):
            if word == "cat":
                entered.set()
                release.wait(2)
            return {"png": word.encode(), "verified": True}
        with patch.object(learning_image, "get_cached_learning_image", return_value=None), \
             patch.object(learning_image, "prepare_learning_image", side_effect=prepare):
            loader = learning_prefetch.LearningImagePrefetch("key", workers=1)
            loader.MAX_ITEMS = 2
            try:
                loader.schedule([{"word": w, "query": w} for w in ("cat", "dog")])
                await asyncio.to_thread(entered.wait, 1)
                foreground = asyncio.create_task(loader.get("bee", "bee"))
                await asyncio.sleep(0.02)
                release.set()
                self.assertEqual((await foreground)["png"], b"bee")
                self.assertLessEqual(len(loader.jobs), 2)
            finally:
                release.set()
                await loader.close()

    async def test_foreground_does_not_wait_for_busy_background_workers(self):
        entered, release = threading.Barrier(4, timeout=2), threading.Event()
        def prepare(query, key, word):
            if word != "current":
                entered.wait()
                release.wait(2)
            return {"png": word.encode(), "verified": True}
        with patch.object(learning_image, "get_cached_learning_image", return_value=None), \
             patch.object(learning_image, "prepare_learning_image", side_effect=prepare):
            loader = learning_prefetch.LearningImagePrefetch("key")
            try:
                loader.schedule([{"word": w, "query": w} for w in ("cat", "dog", "bee", "fish")])
                await asyncio.to_thread(entered.wait)
                image = await loader.get("current", "current", timeout=0.3)
                self.assertEqual(image["png"], b"current")
            finally:
                release.set()
                await loader.close()


if __name__ == "__main__":
    unittest.main()
