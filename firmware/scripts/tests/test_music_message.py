import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class MusicMessageContractTest(unittest.TestCase):
    def test_application_routes_all_tokenized_music_states(self):
        source = (ROOT / "main" / "application.cc").read_text(encoding="utf-8")
        message_header = (ROOT / "main" / "music_message.h").read_text(encoding="utf-8")
        for state in ("start", "cover", "progress", "stop"):
            self.assertIn(f'"{state}"', message_header)
        self.assertIn('"playback_token"', source)
        self.assertIn('"position_ms"', source)
        self.assertIn('"duration_ms"', source)
        self.assertIn("music_playback_token_", source)

    def test_progress_is_validated_and_clamped_before_display(self):
        source = (ROOT / "main" / "application.cc").read_text(encoding="utf-8")
        progress_block = re.search(
            r"MusicMessageState::kProgress.*?MusicMessageState::kStop",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(progress_block)
        block = progress_block.group(0)
        self.assertIn("cJSON_IsNumber", block)
        self.assertRegex(block, r"position_ms\s*>\s*duration_ms")
        self.assertIn("UpdateMusicProgress", block)

    def test_stale_token_is_checked_on_main_task(self):
        source = (ROOT / "main" / "application.cc").read_text(encoding="utf-8")
        self.assertRegex(source, re.compile(
            r"Schedule\(\[.*token.*\].*music_playback_token_\s*!=\s*token",
            re.DOTALL,
        ))


if __name__ == "__main__":
    unittest.main()
