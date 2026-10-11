"""Compile-time behavioral checks for real charging-signal debounce."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ChargingStatusFilterTest(unittest.TestCase):
    def test_signal_glitches_and_plug_unplug_latency(self):
        database = ROOT / 'build' / 'compile_commands.json'
        if not database.exists():
            self.skipTest('A configured firmware compiler is required for C++ behavior checks')
        entries = json.loads(database.read_text())
        compiler_args = json.loads(os.environ['WISIO_TEST_CXX']) if os.environ.get('WISIO_TEST_CXX') else [entries[0]['command'].split(' ', 1)[0]]
        if not Path(compiler_args[0]).exists():
            self.skipTest('Configured ESP-IDF compiler is not available')
        program = r'''
        #include "charging_status_filter.h"
        constexpr bool rejects_glitches() {
            ChargingStatusFilter state;
            if (state.Update(true, 0)) return false;
            if (state.Update(true, 100000)) return false;
            if (state.Update(false, 150000)) return false;
            return !state.Update(false, 400000);
        }
        constexpr bool plugs_and_unplugs_within_three_polls() {
            ChargingStatusFilter state;
            if (state.Update(false, 0)) return false;
            if (state.Update(true, 100000)) return false;
            if (state.Update(true, 200000)) return false;
            if (!state.Update(true, 300000)) return false;
            if (!state.Update(false, 400000)) return false;
            if (!state.Update(false, 500000)) return false;
            return !state.Update(false, 600000);
        }
        constexpr bool unplug_bounce_does_not_flicker() {
            ChargingStatusFilter state;
            state.Update(true, 0);
            if (!state.Update(true, 200000)) return false;
            if (!state.Update(false, 250000)) return false;
            if (!state.Update(true, 300000)) return false;
            if (!state.Update(false, 350000)) return false;
            return state.Update(true, 400000);
        }
        constexpr bool active_low_freenove_signal() {
            ChargingStatusFilter state;
            if (state.UpdateLevel(true, true, 0)) return false;
            if (state.UpdateLevel(true, true, 300000)) return false;
            if (state.UpdateLevel(false, true, 400000)) return false;
            if (!state.UpdateLevel(false, true, 600000)) return false;
            if (!state.UpdateLevel(true, true, 700000)) return false;
            return !state.UpdateLevel(true, true, 900000);
        }
        constexpr bool active_high_boards_unchanged() {
            ChargingStatusFilter state;
            if (state.UpdateLevel(false, false, 0)) return false;
            if (state.UpdateLevel(true, false, 100000)) return false;
            return state.UpdateLevel(true, false, 300000);
        }
        static_assert(rejects_glitches(), "noise must not enter charging mode");
        static_assert(plugs_and_unplugs_within_three_polls(), "charge/remove must settle within 300ms");
        static_assert(unplug_bounce_does_not_flicker(), "noise must not exit a confirmed charging state");
        static_assert(active_low_freenove_signal(), "Freenove CHRG low charges; high does not");
        static_assert(active_high_boards_unchanged(), "existing active-high boards must keep their polarity");
        '''
        result = subprocess.run(
            [*compiler_args, '-std=c++20', '-fsyntax-only', '-x', 'c++',
             '-I', str(ROOT / 'main' / 'boards' / 'common'), '-'],
            input=program, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
