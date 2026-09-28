import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "main/boards/freenove-esp32s3-display-2.8-lcd/freenove-esp32s3-display-2.8-lcd.cc"


class FreenovePowerStartupTests(unittest.TestCase):
    def test_brownout_protection_stays_enabled(self):
        main = (ROOT / "main/main.cc").read_text(encoding="utf-8")
        self.assertNotIn("RTC_CNTL_BROWN_OUT_REG", main)
        self.assertNotIn("WRITE_PERI_REG", main)

    def test_wifi_power_limit_is_applied_before_station_starts(self):
        wifi_board = (ROOT / "main/boards/common/wifi_board.cc").read_text(encoding="utf-8")
        board = BOARD.read_text(encoding="utf-8")
        power = wifi_board.index("GetWifiMaxTxPower")
        connect = wifi_board.index("TryWifiConnect();")
        self.assertLess(power, connect)
        self.assertRegex(board, r"GetWifiMaxTxPower\(\).*return 72")
        self.assertNotRegex(board, r"void StartNetwork\(\) override")

    def test_startup_backlight_avoids_full_power_step(self):
        board = BOARD.read_text(encoding="utf-8")
        match = re.search(r"backlight->SetBrightness\((\d+)\)", board)
        self.assertIsNotNone(match)
        self.assertLessEqual(int(match.group(1)), 60)


if __name__ == "__main__":
    unittest.main()
