"""Run the board's battery-to-application path with a fake ADC and GPIO."""

import json
import os
from pathlib import Path
import subprocess
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


class FreenoveChargeSignalTest(unittest.TestCase):
    def test_adc_estimate_and_unused_gpio_cannot_shut_down_screen(self):
        database = ROOT / "build/compile_commands.json"
        if not database.is_file():
            self.skipTest("A configured compiler is required")
        compiler = json.loads(os.environ["WISIO_TEST_CXX"]) if os.environ.get("WISIO_TEST_CXX") else [
            json.loads(database.read_text())[0]["command"].split(" ", 1)[0]]
        source = (BOARD / "freenove-esp32s3-display-2.8-lcd.cc").read_text(encoding="utf-8")
        update = method(source, "void UpdateChargingScreen(bool charging)").replace(
            "void UpdateChargingScreen", "constexpr void UpdateChargingScreen").replace(
            "Application::GetInstance()", "application")
        battery = method(source, "virtual bool GetBatteryLevel(int& level, bool& charging, bool& discharging) override").replace(
            "virtual bool", "constexpr bool").replace(" override", "")
        program = r'''
        #include "config.h"
        struct State {
            int value = -1;
            constexpr int exchange(int next) { int previous = value; value = next; return previous; }
        };
        struct Display { constexpr bool IsSetupUICalled() const { return true; } };
        struct Monitor {
            int pin = BATTERY_CHARGING_GPIO;
            bool noisy_estimate = true;
            constexpr bool HasChargingStatusSignal() const { return pin != GPIO_NUM_NC; }
            constexpr bool IsCharging() const { return noisy_estimate; }
            constexpr int GetBatteryLevel() const { return 65; }
        };
        struct Application {
            bool asleep = false;
            constexpr void SetChargingMode(bool charging) { asleep = charging; }
        };
        struct Fixture {
            Display display;
            Display* display_ = &display;
            Monitor monitor;
            Monitor* adc_battery_monitor_ = &monitor;
            State charging_screen_state_;
            Application application;
        ''' + update + battery + r'''
        };
        constexpr bool battery_or_usb_noise_never_disables_robot() {
            Fixture robot;
            for (int i = 0; i < 20; ++i) {
                robot.monitor.noisy_estimate = (i % 2 == 0);
                int level = 0; bool charging = true, discharging = false;
                robot.GetBatteryLevel(level, charging, discharging);
                if (charging || !discharging || level != 65 || robot.application.asleep) return false;
                robot.UpdateChargingScreen(true); // stale estimator callback must also be harmless
                if (robot.application.asleep) return false;
            }
            return true;
        }
        static_assert(battery_or_usb_noise_never_disables_robot(),
                      "Unconnected CHRG must never suspend display/audio from GPIO or ADC noise");
        '''
        with tempfile.TemporaryDirectory() as directory:
            include = Path(directory)
            (include / "driver").mkdir()
            (include / "driver/gpio.h").write_text(
                "#pragma once\nenum { GPIO_NUM_NC = -1, GPIO_NUM_3 = 3 };\n")
            result = subprocess.run(
                [*compiler, "-std=c++20", "-fsyntax-only", "-x", "c++", "-I", str(include),
                 "-I", str(BOARD), "-"], input=program, capture_output=True, text=True,
                encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
