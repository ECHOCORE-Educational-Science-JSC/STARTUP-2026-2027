"""Audius source behavior, including use without an optional YouTube install."""

import builtins
import json
import unittest
from unittest.mock import patch

import music


class Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self): return json.dumps({"data": self.data}).encode()


def entry(track_id="aud-1", title="Blue Sky", artist="Luna", **fields):
    return {"id": track_id, "title": title, "user": {"name": artist},
            "duration": 183, "artwork": {"480x480": "https://images.example/art.jpg"},
            "permalink": "/luna/blue-sky", **fields}


class AudiusSourceTest(unittest.TestCase):
    def setUp(self):
        # An uninstalled YouTube extractor must not break any music operation.
        original_import = builtins.__import__

        def without_youtube(name, *args, **kwargs):
            if name == "yt_dlp" or name.startswith("yt_dlp."):
                raise ImportError("YouTube support is not installed")
            return original_import(name, *args, **kwargs)

        importer = patch("builtins.__import__", side_effect=without_youtube)
        importer.start()
        self.addCleanup(importer.stop)
        fallback = patch("music._search_youtube_track", return_value=None)
        fallback.start()
        self.addCleanup(fallback.stop)

    def test_search_works_without_youtube_dependency(self):
        with patch("music.urlopen", return_value=Response([entry()])):
            track = music.search_track("bật nhạc Blue Sky Luna")
        self.assertEqual(track.id, "aud-1")
        self.assertEqual(track.provider, "audius")
        self.assertEqual(track.stream_url, "https://api.audius.co/v1/tracks/aud-1/stream")
        self.assertEqual(track.thumbnail_url, "https://images.example/art.jpg")
        self.assertEqual(track.duration, 183)

    def test_runtime_does_not_need_youtube(self):
        self.assertIsNone(music.runtime_problem())

    def test_empty_catalog_and_empty_fallback_reports_missing_song(self):
        with patch("music.urlopen", return_value=Response([])):
            with self.assertRaisesRegex(music.MusicError, "Audius.*Blue Sky"):
                music.search_track("Blue Sky")

    def test_connection_failure_is_distinct_from_missing_song(self):
        with patch("music.urlopen", side_effect=TimeoutError("offline")):
            with self.assertRaisesRegex(music.MusicError, "Không kết nối được.*Audius"):
                music.search_track("Blue Sky")

    def test_gated_or_failed_tracks_do_not_hide_playable_match(self):
        data = [entry("gated", is_stream_gated=True), entry("dead"), entry("working")]
        with patch("music.urlopen", return_value=Response(data)):
            track = music.search_track("Blue Sky Luna", {"dead"})
        self.assertEqual(track.id, "working")

    def test_rejects_similar_title_by_wrong_artist(self):
        with patch("music.urlopen", return_value=Response([
                entry(title="The Blue Sky Speaks", artist="Lunazaki")])):
            with self.assertRaises(music.MusicError):
                music.search_track("Blue Sky Luna")

    def test_broad_request_can_select_a_public_track(self):
        with patch("music.urlopen", return_value=Response([
                entry(title="Sunny Morning", artist="Luna")])):
            track = music.search_track("bật nhạc")
        self.assertEqual(track.title, "Sunny Morning")

    def test_refresh_rejects_invalid_youtube_id(self):
        track = music.Track("old", "Old", "Artist", "https://stream.example",
                            "https://youtube.example/watch", provider="youtube")
        with self.assertRaisesRegex(music.MusicError, "không hợp lệ"):
            music.refresh_track_stream(track)


if __name__ == "__main__":
    unittest.main()
