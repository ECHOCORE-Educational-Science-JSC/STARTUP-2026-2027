"""Provider fallback at the external HTTP/extractor boundary."""

import sys
import types
import unittest
from unittest.mock import patch

import music


def video(video_id="abcdefghijk", title="Blue Sky", artist="Luna", **extra):
    return dict(id=video_id, title=title, uploader=artist, duration=180, **extra)


class YouTubeFallbackTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.options = []
        self.entries = [video()]
        self.details = {}
        owner = self

        class Extractor:
            def __init__(self, options): owner.options.append(options)
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def extract_info(self, url, download=False):
                owner.calls.append(url)
                if url.startswith("ytsearch"):
                    return {"entries": owner.entries}
                result = owner.details.get(url, {
                    **video(), "url": "https://audio.example/fresh",
                    "thumbnail": "https://images.example/cover.jpg",
                    "http_headers": {"User-Agent": "test-player"}})
                if isinstance(result, Exception): raise result
                return result

        module = types.ModuleType("yt_dlp")
        module.YoutubeDL = Extractor
        for patcher in (
            patch.dict(sys.modules, {"yt_dlp": module}),
            patch.object(music, "runtime_problem", return_value=None),
            patch.object(music, "_search_audius_track", return_value=None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_missing_audius_song_resolves_youtube_audio_and_metadata(self):
        track = music.search_track("Blue Sky Luna")
        self.assertEqual(track.provider, "youtube")
        self.assertEqual(track.stream_url, "https://audio.example/fresh")
        self.assertEqual(track.display_title, "Blue Sky")
        self.assertEqual(track.http_headers["User-Agent"], "test-player")
        self.assertTrue(self.options[0]["extract_flat"])

    def test_audius_remains_first_choice(self):
        audius = music.Track("aud", "Blue Sky", "Luna")
        with patch.object(music, "_search_audius_track", return_value=audius):
            self.assertIs(music.search_track("Blue Sky Luna"), audius)
        self.assertEqual(self.calls, [])

    def test_audius_network_failure_can_fall_back_to_youtube(self):
        with patch.object(music, "_search_audius_track", side_effect=music.MusicError("offline")):
            self.assertEqual(music.search_track("Blue Sky Luna").provider, "youtube")

    def test_unavailable_best_candidate_does_not_hide_next_match(self):
        self.entries = [video(), video("lmnopqrstuv")]
        self.details["https://www.youtube.com/watch?v=abcdefghijk"] = RuntimeError("Video unavailable")
        self.details["https://www.youtube.com/watch?v=lmnopqrstuv"] = {
            **video("lmnopqrstuv"), "url": "https://audio.example/second"}
        track = music.search_track("Blue Sky Luna")
        self.assertEqual(track.id, "lmnopqrstuv")

    def test_failed_and_unrelated_candidates_are_not_extracted(self):
        self.entries = [video(), video("lmnopqrstuv", "Different Song", "Someone")]
        with self.assertRaises(music.MusicError):
            music.search_track("Blue Sky Luna", {"abcdefghijk"})
        self.assertEqual(len(self.calls), 1)

    def test_refresh_renews_signed_url_without_changing_requested_song(self):
        old = music.Track("abcdefghijk", "Blue Sky", "Luna", "https://expired.example",
                          "https://www.youtube.com/watch?v=abcdefghijk", provider="youtube")
        fresh = music.refresh_track_stream(old)
        self.assertEqual(fresh.stream_url, "https://audio.example/fresh")
        self.assertEqual(fresh.provider, "youtube")
        self.assertEqual(fresh.title, old.title)

    def test_refresh_does_not_follow_arbitrary_webpage(self):
        bad = music.Track("not-an-id", "Blue Sky", "Luna", webpage_url="http://localhost/admin",
                          provider="youtube")
        with self.assertRaises(music.MusicError): music.refresh_track_stream(bad)
        self.assertEqual(self.calls, [])

    def test_resolved_wrong_metadata_is_rejected(self):
        self.details["https://www.youtube.com/watch?v=abcdefghijk"] = {
            **video(title="Different Song", artist="Someone"), "url": "https://audio.example/wrong"}
        with self.assertRaises(music.MusicError): music.search_track("Blue Sky Luna")

    def test_live_or_age_restricted_result_is_skipped(self):
        self.entries = [video(is_live=True), video("lmnopqrstuv", age_limit=18)]
        with self.assertRaises(music.MusicError): music.search_track("Blue Sky Luna")
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__": unittest.main()
