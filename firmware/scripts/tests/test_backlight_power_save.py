"""Execute production backlight methods at compile time with a fake LED/timer."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


def method(source, name):
    start = source.index(f"void Backlight::{name}(")
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end].replace("void Backlight::", "constexpr void Fixture::").replace(
        "std::lock_guard<std::mutex>", "Lock")


class BacklightPowerSaveTest(unittest.TestCase):
    def test_real_methods_cannot_relight_a_charging_display(self):
        database = ROOT / "build/compile_commands.json"
        if not database.is_file():
            self.skipTest("A configured compiler is required")
        compiler = json.loads(os.environ["WISIO_TEST_CXX"]) if os.environ.get("WISIO_TEST_CXX") else [
            json.loads(database.read_text())[0]["command"].split(" ", 1)[0]]
        source = (ROOT / "main/boards/common/backlight.cc").read_text(encoding="utf-8")
        program = r'''
        #include <cstdint>
        #define ESP_LOGI(...) ((void)0)
        struct Mutex {};
        struct Lock { constexpr Lock(Mutex&) {} };
        struct Settings {
            constexpr Settings(const char*, bool) {}
            constexpr void SetInt(const char*, int) {}
        };
        struct Fixture {
            void* transition_timer_ = this;
            uint8_t brightness_ = 0, target_brightness_ = 0, step_ = 1, hardware = 0;
            bool power_save_ = false, timer_running = false;
            Mutex transition_mutex_;
            constexpr void SetBrightness(uint8_t brightness, bool permanent = false);
            constexpr void SetPowerSaveMode(bool on);
            constexpr void OnTransitionTimer();
            constexpr void SetBrightnessImpl(uint8_t value) { hardware = value; }
            constexpr void esp_timer_stop(void*) { timer_running = false; }
            constexpr void esp_timer_start_periodic(void*, int) { timer_running = true; }
            constexpr void settle() { for (int i = 0; i < 100; ++i) OnTransitionTimer(); }
        };
        '''
        program += "\n".join(method(source, name) for name in (
            "SetBrightness", "SetPowerSaveMode", "OnTransitionTimer"))
        program += r'''
        constexpr bool charging_stays_dark_and_restores_desired_brightness() {
            Fixture light;
            light.SetBrightness(75);
            light.settle();
            if (light.hardware != 75 || light.timer_running) return false;
            light.SetPowerSaveMode(true);
            if (light.hardware != 0 || light.timer_running) return false;
            light.SetBrightness(45); // queued startup fade / UI / MCP request
            light.settle();
            light.SetPowerSaveMode(true); // duplicate charge notification
            if (light.hardware != 0 || light.timer_running) return false;
            light.SetPowerSaveMode(false);
            light.settle();
            return light.hardware == 45 && !light.timer_running;
        }
        constexpr bool turning_off_cancels_an_old_ramp() {
            Fixture light;
            light.SetBrightness(75);
            light.SetBrightness(0);
            light.settle();
            return light.hardware == 0 && !light.timer_running;
        }
        constexpr bool charge_interrupts_a_fade_immediately() {
            Fixture light;
            light.SetBrightness(75);
            for (int i = 0; i < 10; ++i) light.OnTransitionTimer();
            light.SetPowerSaveMode(true);
            light.settle();
            return light.hardware == 0 && !light.timer_running;
        }
        static_assert(charging_stays_dark_and_restores_desired_brightness());
        static_assert(turning_off_cancels_an_old_ramp());
        static_assert(charge_interrupts_a_fade_immediately());
        '''
        result = subprocess.run([*compiler, "-std=c++20", "-fsyntax-only", "-x", "c++", "-"],
                                input=program, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
