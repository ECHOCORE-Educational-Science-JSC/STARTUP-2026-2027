"""Cancelled image waiters must not log background failures on Python 3.14."""

import asyncio
from contextlib import redirect_stdout
import io
import threading
import unittest
from unittest.mock import patch

import learning_image
import learning_prefetch


class PrefetchCancellationCleanupTest(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_waiter_records_late_failure_without_event_loop_error(self):
        await self.check_late_failure(timeout=False, another_waiter=False)

    async def test_timed_out_waiter_records_late_failure_without_event_loop_error(self):
        await self.check_late_failure(timeout=True, another_waiter=False)

    async def test_cancelled_waiter_preserves_another_waiters_failure(self):
        await self.check_late_failure(timeout=False, another_waiter=True)

    async def check_late_failure(self, timeout, another_waiter):
        loop = asyncio.get_running_loop()
        worker_started, job_finished = asyncio.Event(), asyncio.Event()
        release_worker = threading.Event()
        errors = []
        old_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda event_loop, context: errors.append(context))
        expected_error = learning_image.LearningImageError("controlled old image timeout")
        loader = learning_prefetch.LearningImagePrefetch("unused-test-key", workers=1)
        second_waiter = None

        def prepare(query, api_key, word):
            loop.call_soon_threadsafe(worker_started.set)
            if not release_worker.wait(3):
                raise AssertionError("Test failed to release its image worker")
            raise expected_error

        with patch.object(learning_image, "get_cached_learning_image", return_value=None), \
             patch.object(learning_image, "prepare_learning_image", prepare), \
             redirect_stdout(io.StringIO()):
            waiter = asyncio.create_task(loader.get("orange cat photo", "cat", timeout=0.02 if timeout else 3))
            try:
                await asyncio.wait_for(worker_started.wait(), 2)
                shared_job = loader.jobs[("orange cat photo", "cat")]["future"]
                shared_job.add_done_callback(lambda future: job_finished.set())
                if another_waiter:
                    second_waiter = asyncio.create_task(loader.get("orange cat photo", "cat", timeout=3))
                    # Allow its cache lookup and foreground submission to finish.
                    await asyncio.sleep(0.01)
                if timeout:
                    with self.assertRaises(TimeoutError):
                        await waiter
                else:
                    waiter.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await waiter
                self.assertFalse(shared_job.done(),
                                 "Cancelling or timing out a waiter must preserve useful shared work")
                release_worker.set()
                await asyncio.wait_for(job_finished.wait(), 2)
                # Done callbacks must have run before inspecting the exception log.
                await asyncio.sleep(0)
                if second_waiter is not None:
                    with self.assertRaises(learning_image.LearningImageError) as failure:
                        await second_waiter
                    self.assertIs(failure.exception, expected_error)
                self.assertIs(shared_job.exception(), expected_error,
                              "The real background failure must remain recorded")
                self.assertEqual(errors, [],
                                 "A cancelled foreground wait must not create a shielded-future traceback")
            finally:
                release_worker.set()
                for task in (waiter, second_waiter):
                    if task is not None and not task.done():
                        task.cancel()
                await asyncio.gather(*(task for task in (waiter, second_waiter)
                                       if task is not None), return_exceptions=True)
                await loader.close()
                loop.set_exception_handler(old_handler)

    async def test_cancelled_waiter_keeps_verified_result_for_next_request(self):
        loop = asyncio.get_running_loop()
        worker_started, job_finished = asyncio.Event(), asyncio.Event()
        release_worker = threading.Event()
        visual = {"verified": True, "png": b"verified picture", "source_title": "Orange cat"}
        loader = learning_prefetch.LearningImagePrefetch("unused-test-key", workers=1)
        calls = []

        def prepare(query, api_key, word):
            calls.append((query, word))
            loop.call_soon_threadsafe(worker_started.set)
            if not release_worker.wait(3):
                raise AssertionError("Test failed to release its image worker")
            return visual

        with patch.object(learning_image, "get_cached_learning_image", return_value=None), \
             patch.object(learning_image, "prepare_learning_image", prepare), \
             redirect_stdout(io.StringIO()):
            waiter = asyncio.create_task(loader.get("orange cat photo", "cat"))
            try:
                await asyncio.wait_for(worker_started.wait(), 2)
                shared_job = loader.jobs[("orange cat photo", "cat")]["future"]
                shared_job.add_done_callback(lambda future: job_finished.set())
                waiter.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await waiter
                self.assertFalse(shared_job.done())
                release_worker.set()
                await asyncio.wait_for(job_finished.wait(), 2)
                self.assertEqual(await loader.get("orange cat photo", "cat"), visual)
                self.assertEqual(calls, [("orange cat photo", "cat")],
                                 "A later valid request must reuse the completed shared image")
            finally:
                release_worker.set()
                if not waiter.done():
                    waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
                await loader.close()


if __name__ == "__main__":
    unittest.main()
