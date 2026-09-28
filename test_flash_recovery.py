import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class FlashRecoveryScriptTests(unittest.TestCase):
    def test_recovery_flash_does_not_reopen_monitor(self):
        script = (ROOT / "flash_wisio.ps1").read_text(encoding="utf-8")
        self.assertIn('idf_monitor\\.py', script)
        self.assertIn("Stop-Process", script)
        self.assertRegex(script, r"idf\.py.*flash")
        flash_line = next(line for line in script.splitlines() if "idf.py" in line and "flash" in line)
        self.assertNotIn("monitor", flash_line.casefold())
        self.assertIn("115200", flash_line)


if __name__ == "__main__":
    unittest.main()
