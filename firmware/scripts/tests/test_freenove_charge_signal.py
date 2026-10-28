"""The mains-powered Freenove must not report, monitor or react to a battery."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "main/boards/freenove-esp32s3-display-2.8-lcd"


def method(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class FreenoveMainsPowerTest(unittest.TestCase):
    def test_no_adc_monitor_or_charging_callback_is_registered(self):
        source = (BOARD / "freenove-esp32s3-display-2.8-lcd.cc").read_text(encoding="utf-8")
        self.assertNotIn('AdcBatteryMonitor', source)
        self.assertNotIn('InitializeBatteryMonitor', source)
        self.assertNotIn('SetChargingMode', source)
        self.assertNotIn('UpdateChargingScreen', source)

    def test_battery_contract_is_unsupported_and_never_reports_low_or_charging(self):
        compiler_path = shutil.which('g++') or 'C:/Program Files/CodeBlocks/MinGW/bin/g++.exe'
        if not Path(compiler_path).is_file():
            self.skipTest('Host C++ compiler unavailable')
        compiler = [compiler_path]
        source = (BOARD / "freenove-esp32s3-display-2.8-lcd.cc").read_text(encoding="utf-8")
        battery = method(source, "virtual bool GetBatteryLevel(int& level, bool& charging, bool& discharging) override").replace(
            "virtual bool", "constexpr bool").replace(" override", "")
        program = "struct Board {" + battery + "};" + r"""
        constexpr bool mains_has_no_battery_state() {
            Board board;
            int inputs[] = {0, 1, 50, 100, -1};
            for (int initial : inputs) {
                int level = initial;
                bool charging = true, discharging = true;
                if (board.GetBatteryLevel(level, charging, discharging)) return false;
                if (level != 0 || charging || discharging) return false;
            }
            return true;
        }
        static_assert(mains_has_no_battery_state(), "No battery means no low-battery popup or charging state");
        """
        with tempfile.TemporaryDirectory(dir=ROOT / 'test-tmp') as directory:
            result = subprocess.run([*compiler, "-std=c++20", "-fsyntax-only", "-x", "c++", "-"],
                                    input=program, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
