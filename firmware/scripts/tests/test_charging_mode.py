from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ChargingModeSourceTest(unittest.TestCase):
    def test_charging_mode_gates_all_conversation_audio(self):
        source = (ROOT / "main" / "application.cc").read_text(encoding="utf-8")
        self.assertIn("charging_mode_.exchange(charging)", source)
        self.assertIn("codec->EnableInput(false)", source)
        self.assertIn("codec->EnableOutput(false)", source)
        self.assertIn("if (charging_mode_.load()) {\n            return;\n        }\n        if (GetDeviceState() == kDeviceStateSpeaking)", source)
        self.assertIn('ESP_LOGD(TAG, "Ignored %s while charging"', source)
        self.assertIn("if (!charging_mode_.load()) audio_service_.PlaySound(sound)", source)

    def test_charging_overlay_overscans_and_has_no_default_style(self):
        source = (ROOT / "main" / "display" / "lcd_display.cc").read_text(encoding="utf-8")
        self.assertIn("lv_obj_create(lv_layer_top())", source)
        self.assertIn("lv_obj_remove_style_all(charging_overlay_)", source)
        self.assertIn("lv_obj_set_pos(charging_overlay_, -2, -2)", source)
        self.assertIn("LV_HOR_RES + 4, LV_VER_RES + 4", source)


if __name__ == "__main__":
    unittest.main()
