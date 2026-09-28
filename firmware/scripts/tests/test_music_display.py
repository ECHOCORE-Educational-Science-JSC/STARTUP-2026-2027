import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class MusicDisplayContractTest(unittest.TestCase):
    def test_board_neutral_display_has_music_api(self):
        header = (ROOT / "main" / "display" / "display.h").read_text(encoding="utf-8")
        source = (ROOT / "main" / "display" / "display.cc").read_text(encoding="utf-8")
        for method in ("ShowMusicPlayer", "UpdateMusicProgress", "HideMusicPlayer"):
            self.assertIn(method, header)
            self.assertIn(f"Display::{method}", source)

    def test_lcd_player_has_persistent_cover_progress_and_unknown_duration(self):
        header = (ROOT / "main" / "display" / "lcd_display.h").read_text(encoding="utf-8")
        source = (ROOT / "main" / "display" / "lcd_display.cc").read_text(encoding="utf-8")
        self.assertIn("SetMusicCover", header)
        self.assertIn("music_progress_bar_", header)
        self.assertIn("lv_bar_set_range(music_progress_bar_, 0, 1000)", source)
        self.assertIn('"--:--"', source)
        self.assertIn("esp_timer_stop(preview_timer_)", source)
        self.assertIn("music_cover_cached_.reset()", source)

    def test_music_time_uses_minute_second_format(self):
        source = (ROOT / "main" / "display" / "lcd_display.cc").read_text(encoding="utf-8")
        self.assertIn("FormatMusicTime", source)
        self.assertIn('"%02lu:%02lu"', source)

    def test_idle_and_physical_abort_clear_the_music_overlay(self):
        source = (ROOT / "main" / "application.cc").read_text(encoding="utf-8")
        idle_case = source.split("case kDeviceStateIdle:", 1)[1].split(
            "case kDeviceStateConnecting:", 1
        )[0]
        abort_body = source.split("void Application::AbortSpeaking", 1)[1].split(
            "void Application::SetListeningMode", 1
        )[0]
        self.assertIn("music_playback_token_.clear()", idle_case)
        self.assertIn("display->HideMusicPlayer()", idle_case)
        self.assertIn("music_playback_token_.clear()", abort_body)
        self.assertIn("HideMusicPlayer()", abort_body)


if __name__ == "__main__":
    unittest.main()
