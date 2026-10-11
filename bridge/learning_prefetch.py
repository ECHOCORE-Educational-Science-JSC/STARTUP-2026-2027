"""Bounded image preparation with foreground priority and no background display."""

from __future__ import annotations

import asyncio
import itertools
import time

import learning_image


class LearningImagePrefetch:
    MAX_ITEMS = 64

    def __init__(self, api_key: str, workers: int = 4):
        self.api_key = api_key
        self.worker_count = max(1, min(workers, 4))
        self.queue = asyncio.PriorityQueue()
        self.foreground_queue = asyncio.PriorityQueue()
        self.sequence = itertools.count()
        self.jobs = {}
        self.workers = []
        self.closed = False

    @staticmethod
    def _key(query: str, word: str) -> tuple[str, str]:
        return (" ".join(str(query).split()).casefold(),
                " ".join(str(word).split()).casefold())

    def _submit(self, query: str, word: str, priority: int):
        if self.closed:
            raise learning_image.LearningImageError("Bài học đã kết thúc.")
        key = self._key(query, word)
        job = self.jobs.get(key)
        if job is not None and priority == 0 and job["foreground_claimed"] and job["future"].done() and (
                job["future"].cancelled() or job["future"].exception() is not None):
            del self.jobs[key]
            job = None
        if job is not None:
            if priority == 0:
                job['foreground_claimed'] = True
            if priority < job["priority"] and not job["running"] and not job["future"].done():
                job["priority"] = priority
                self._enqueue(priority, key)
            return job["future"]
        # Evict finished jobs only: never cancel useful preparation to add more.
        if len(self.jobs) >= self.MAX_ITEMS:
            for old_key in list(self.jobs):
                if self.jobs[old_key]["future"].done():
                    del self.jobs[old_key]
                    break
        if len(self.jobs) >= self.MAX_ITEMS:
            if priority == 0:
                for old_key, old_job in reversed(tuple(self.jobs.items())):
                    if not old_job["running"] and old_job["priority"] > priority:
                        old_job["future"].cancel()
                        del self.jobs[old_key]
                        break
        if len(self.jobs) >= self.MAX_ITEMS:
            return None
        future = asyncio.get_running_loop().create_future()
        # Background failures are recorded for a foreground caller, not emitted
        # as unhandled-future errors when a lesson changes before reaching them.
        future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        self.jobs[key] = {"query": query, "word": word, "priority": priority,
                          "running": False, "future": future, 'foreground_claimed': priority == 0}
        self._enqueue(priority, key)
        if not self.workers:
            # Reserve one slot at the normal four-worker setting so a new
            # foreground image isn't held behind several slow background searches.
            background_workers = self.worker_count - (1 if self.worker_count == 4 else 0)
            self.workers = [asyncio.create_task(self._worker(self.queue))
                            for _ in range(background_workers)]
            if self.worker_count == 4:
                self.workers.append(asyncio.create_task(self._worker(self.foreground_queue)))
        return future

    def _enqueue(self, priority: int, key):
        entry = (priority, next(self.sequence), key)
        self.queue.put_nowait(entry)
        if priority == 0 and self.worker_count == 4:
            self.foreground_queue.put_nowait(entry)

    def schedule(self, items: list[dict]) -> int:
        accepted = 0
        for item in items[:self.MAX_ITEMS]:
            if not isinstance(item, dict):
                continue
            word = " ".join(str(item.get("word") or "").split())[:120]
            query = " ".join(str(item.get("query") or word).split())[:1200]
            if word and query and self._submit(query, word, 1) is not None:
                accepted += 1
        return accepted

    async def _worker(self, queue):
        while True:
            priority, _, key = await queue.get()
            try:
                job = self.jobs.get(key)
                if job is None or job["running"] or job["future"].done() or priority != job["priority"]:
                    continue
                job["running"] = True
                started = time.monotonic()
                try:
                    visual = await asyncio.to_thread(
                        learning_image.prepare_learning_image,
                        job["query"], self.api_key, job["word"])
                    if visual.get("verified") is not True:
                        raise learning_image.LearningImageError("Ảnh chưa được xác minh, không hiển thị.")
                    if not job["future"].done():
                        job["future"].set_result(visual)
                    print(f"[IMAGE PREFETCH] Ready: {job['word']} ({time.monotonic()-started:.2f}s)")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if not job["future"].done():
                        job["future"].set_exception(exc)
                    description = str(exc)
                    if self.api_key:
                        description = description.replace(self.api_key, '[REDACTED]')
                    description = ' '.join(description.split())[:250]
                    print(f"[IMAGE PREFETCH] Skipped {job['word']}: {type(exc).__name__}: {description}")
            finally:
                queue.task_done()

    async def get(self, query: str, word: str, timeout: float = 30) -> dict:
        started = time.monotonic()
        cached = await asyncio.to_thread(learning_image.get_cached_learning_image, query, word)
        if cached is not None and cached.get("verified") is True:
            print(f"[IMAGE CACHE] Hit: {word} ({time.monotonic()-started:.3f}s)")
            return cached
        future = self._submit(query, word, 0)
        if future is None:
            raise learning_image.LearningImageError("Hàng đợi ảnh đang đầy. Bé thử lại nhé.")
        # A caller's timeout must not cancel useful work shared by a later call.
        # On Python 3.14 shield logs a late inner exception after its waiter
        # is cancelled. Observe readiness without cancelling shared preparation.
        done, _ = await asyncio.wait({future}, timeout=timeout)
        if not done:
            raise TimeoutError
        return future.result()

    async def close(self):
        self.closed = True
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        for job in self.jobs.values():
            if not job["future"].done():
                job["future"].cancel()
        self.jobs.clear()
        for queue in (self.queue, self.foreground_queue):
            while not queue.empty():
                queue.get_nowait()
                queue.task_done()
