"""Compile the production registration flow against an ESP-SR lifecycle fake."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CustomWakeRegistryTest(unittest.TestCase):
    def test_registry_is_bound_before_adding_commands_and_failures_are_rejected(self):
        database = ROOT / "build/compile_commands.json"
        if not database.exists():
            self.skipTest("A configured compiler is required")
        compiler = json.loads(os.environ["WISIO_TEST_CXX"]) if os.environ.get("WISIO_TEST_CXX") else [
            json.loads(database.read_text())[0]["command"].split(" ", 1)[0]]
        source = (ROOT / "main/audio/wake_words/custom_wake_word.cc").read_text(encoding="utf-8")
        start = source.index("    multinet_ = esp_mn_handle_from_name(mn_name_);")
        stop = source.index("#if CONFIG_SEND_WAKE_WORD_DATA", start)
        registration = source[start:stop]
        program = r'''
        #include <array>
        #include <cstddef>
        using std::size_t;
        #define ESP_OK 0
        #define ESP_LOGE(...) ((void)0)
        struct Token { constexpr const char* c_str() const { return "HEY WISIO"; } };
        struct Command { Token command; };
        struct Buffer { constexpr void reserve(int) {} };
        struct Interface {
            bool fail_model = false;
            constexpr void* create(const char*, int) { return fail_model ? nullptr : this; }
            constexpr void set_det_threshold(void*, float) {}
            constexpr int get_samp_chunksize(void*) { return 480; }
            constexpr void print_active_speech_commands(void*) {}
        };
        struct Fixture {
            Interface iface;
            Interface* multinet_ = nullptr;
            void* multinet_model_data_ = nullptr;
            const char* mn_name_ = "mn6_en";
            int duration_ = 3000;
            float threshold_ = 0.7f;
            Buffer input_buffer_;
            std::array<Command, 1> commands_{};
            bool commands_allocated_ = false, registry = false, added = false, updated = false;
            bool fail_alloc = false, fail_add = false, fail_update = false;
            constexpr Interface* esp_mn_handle_from_name(const char*) { return &iface; }
            constexpr int esp_mn_commands_alloc(Interface* api, void* data) {
                if (fail_alloc || api != &iface || data != &iface) return -1;
                registry = true;
                return 0;
            }
            constexpr int esp_mn_commands_clear() { return registry ? 0 : -1; }
            constexpr int esp_mn_commands_add(int, const char*) {
                if (!registry || fail_add) return -1;
                added = true;
                return 0;
            }
            constexpr const char* esp_mn_commands_update() {
                if (!added || fail_update) return "invalid";
                updated = true;
                return nullptr;
            }
            constexpr bool initialize() {
        ''' + registration + r'''
                return true;
            }
        };
        constexpr bool validates_registry_lifecycle() {
            Fixture good;
            if (!good.initialize() || !good.commands_allocated_ || !good.updated) return false;
            Fixture no_model;
            no_model.iface.fail_model = true;
            if (no_model.initialize() || no_model.registry) return false;
            Fixture no_registry;
            no_registry.fail_alloc = true;
            if (no_registry.initialize() || no_registry.added) return false;
            Fixture bad_phrase;
            bad_phrase.fail_add = true;
            if (bad_phrase.initialize() || bad_phrase.updated) return false;
            Fixture rejected;
            rejected.fail_update = true;
            return !rejected.initialize();
        }
        static_assert(validates_registry_lifecycle());
        '''
        result = subprocess.run([*compiler, "-std=c++20", "-fsyntax-only", "-x", "c++", "-"],
                                input=program, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
