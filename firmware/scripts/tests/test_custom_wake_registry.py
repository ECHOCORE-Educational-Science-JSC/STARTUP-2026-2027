"""Compile the production registration flow against an ESP-SR lifecycle fake."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CustomWakeRegistryTest(unittest.TestCase):
    def test_wake_notification_never_waits_for_the_afe_feed_mutex(self):
        import test_protocol_safety as protocol_tests
        from test_server_greeting import method_source
        source = (ROOT / 'main/audio/engines/afe_audio_engine.cc').read_text(encoding='utf-8')
        notify = method_source(source, 'void AfeAudioEngine::NotifyWakeWordDetected(')
        program = r'''
#include <cassert>
#include <atomic>
#include <functional>
#include <mutex>
#include <string>
constexpr unsigned kWakeWordEnabled=1;
unsigned bits=1;
void xEventGroupClearBits(int,unsigned value){bits&=~value;}
struct AfeAudioEngine{
 std::mutex input_buffer_mutex_;int event_group_=0;
 std::string last_detected_wake_word_;std::atomic<bool> afe_control_dirty_{false};
 std::function<void(const std::string&)> wake_word_detected_callback_;
 void NotifyWakeWordDetected(const std::string&);
};
''' + notify + r'''
int main(){
 AfeAudioEngine engine;int callbacks=0;
 engine.wake_word_detected_callback_=[&](const std::string& word){assert(word=="Hey Wisio");++callbacks;};
 std::lock_guard<std::mutex> feed_busy(engine.input_buffer_mutex_);
 engine.NotifyWakeWordDetected("Hey Wisio");
 assert(callbacks==1&&bits==0&&engine.afe_control_dirty_);
 return 0;
}
'''
        protocol_tests.ProtocolSafetyTests.compile_run(self, program)

    def test_detection_callback_can_stop_detector_without_locking_itself(self):
        import test_protocol_safety as protocol_tests
        from test_server_greeting import method_source
        source = (ROOT / 'main/audio/wake_words/custom_wake_word.cc').read_text(encoding='utf-8')
        feed = method_source(source, 'void CustomWakeWord::FeedSamples(')
        stop = method_source(source, 'void CustomWakeWord::Stop(')
        program = r'''
#include <cassert>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <functional>
#include <mutex>
#include <string>
#include <vector>
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
#define ESP_MN_RESULT_MAX_NUM 5
enum esp_mn_state_t{ESP_MN_STATE_DETECTING,ESP_MN_STATE_DETECTED,ESP_MN_STATE_TIMEOUT};
struct esp_mn_results_t{int num=1;int command_id[5]{1};float prob[5]{0.8f};const char* string="hey wisio";};
struct Model{
 esp_mn_results_t result;esp_mn_state_t state=ESP_MN_STATE_DETECTED;bool missing=false;int resets=0;
 int get_samp_chunksize(void*){return 4;}esp_mn_state_t detect(void*,const int16_t*){return state;}
 esp_mn_results_t* get_results(void*){return missing?nullptr:&result;}
 void clean(void*){++resets;}
};
struct Codec{int input_channels(){return 1;}};
struct CustomWakeWord{
 Codec codec;Codec* codec_=&codec;Model model;Model* multinet_=&model;void* multinet_model_data_=&model;
 std::mutex input_buffer_mutex_;std::atomic<bool> running_{true};std::vector<int16_t> input_buffer_;
 size_t diagnostic_samples_=0,diagnostic_clipped_=0;uint64_t diagnostic_energy_=0;
 int diagnostic_peak_=0;unsigned diagnostic_detections_=0,diagnostic_timeouts_=0;
 float threshold_=0.55f;std::string last_detected_wake_word_;
 struct Command{std::string action,text;};std::vector<Command> commands_{{"wake","Hey Wisio"}};
 std::function<void(const std::string&)> wake_word_detected_callback_;
 void FeedSamples(const int16_t*,size_t,bool);void Stop();
};
''' + feed + stop + r'''
int main(){
 CustomWakeWord wake;int callbacks=0;const int16_t pcm[4]{100,-200,300,-400};
 wake.wake_word_detected_callback_=[&](const std::string& word){
  assert(word=="Hey Wisio");++callbacks;wake.Stop();
 };
 wake.FeedSamples(pcm,4,true);assert(callbacks==1&&!wake.running_&&wake.input_buffer_.empty());
 wake.FeedSamples(pcm,4,true);assert(callbacks==1);
 wake.running_=true;wake.model.result.command_id[0]=0;wake.FeedSamples(pcm,4,true);assert(callbacks==1);
 wake.model.result.command_id[0]=1;wake.model.result.prob[0]=NAN;
 wake.FeedSamples(pcm,4,true);assert(callbacks==1);
 wake.model.result.prob[0]=0.5;wake.FeedSamples(pcm,4,true);assert(callbacks==1);
 wake.model.missing=true;wake.FeedSamples(pcm,4,true);assert(callbacks==1);
 wake.model.missing=false;wake.model.result.prob[0]=0.8;
 wake.FeedSamples(pcm,4,true);assert(callbacks==2);
 return 0;
}
'''
        protocol_tests.ProtocolSafetyTests.compile_run(self, program)

    def test_disabled_wake_upload_never_starts_encoder_or_waits_for_packets(self):
        source = (ROOT / 'main/audio/audio_service.cc').read_text(encoding='utf-8')
        encode = source[source.index('void AudioService::EncodeWakeWord()'):
                        source.index('const std::string& AudioService::GetLastWakeWord()')]
        pop = source[source.index('std::unique_ptr<AudioStreamPacket> AudioService::PopWakeWordPacket()'):
                     source.index('void AudioService::SetSuspended(')]
        program = r'''
        #include <memory>
        #include <vector>
        #include <cassert>
        struct AudioStreamPacket { std::vector<unsigned char> payload; };
        struct Engine {
            int encoded = 0, popped = 0;
            void EncodeWakeWordData() { ++encoded; }
            bool GetWakeWordOpus(std::vector<unsigned char>&) { return ++popped == 1; }
        };
        struct AudioService {
            Engine* audio_engine_;
            void EncodeWakeWord();
            std::unique_ptr<AudioStreamPacket> PopWakeWordPacket();
        };
        ''' + encode + pop + r'''
        int main() {
            Engine engine;
            AudioService audio{&engine};
            audio.EncodeWakeWord();
            auto packet = audio.PopWakeWordPacket();
            #if CONFIG_SEND_WAKE_WORD_DATA
            assert(engine.encoded == 1 && engine.popped == 1 && packet);
            assert(!audio.PopWakeWordPacket());
            #else
            assert(engine.encoded == 0 && engine.popped == 0 && !packet);
            #endif
            AudioService missing{nullptr};
            missing.EncodeWakeWord();
            assert(!missing.PopWakeWordPacket());
        }
        '''
        import tempfile
        compiler = json.loads(os.environ.get('WISIO_TEST_CXX', '["g++"]'))
        with tempfile.TemporaryDirectory() as directory:
            for enabled in [0, 1]:
                binary = str(Path(directory) / f'upload-{enabled}.exe')
                result = subprocess.run([*compiler, '-std=c++20', f'-DCONFIG_SEND_WAKE_WORD_DATA={enabled}',
                                         '-x', 'c++', '-', '-o', binary], input=program,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                subprocess.run([binary], check=True, timeout=10)

    def test_multinet_does_not_enable_self_wake_during_playback(self):
        source = (ROOT / 'main/audio/engines/afe_audio_engine.h').read_text()
        method = source.split('bool IsAfeWakeWord() const override {', 1)[1].split('}', 1)[0]
        compiler = json.loads(os.environ.get('WISIO_TEST_CXX', '["g++"]'))
        program = '''
        enum class WakeDetector { kNone, kWakeNet, kMultiNet };
        struct Codec { bool reference; constexpr bool input_reference() const { return reference; } };
        struct Engine {
            WakeDetector wake_detector_;
            const Codec* codec_ = nullptr;
            constexpr bool HasWakeWord() const { return wake_detector_ != WakeDetector::kNone; }
            constexpr bool IsAfeWakeWord() const {
        ''' + method + '''
            }
        };
        constexpr Engine custom{WakeDetector::kMultiNet};
        static_assert(custom.HasWakeWord());
        static_assert(!custom.IsAfeWakeWord());
        static_assert(Engine{WakeDetector::kWakeNet}.IsAfeWakeWord());
        static_assert(!Engine{WakeDetector::kNone}.IsAfeWakeWord());
        constexpr Codec mic_only{false}, echo_reference{true};
        static_assert(!Engine{WakeDetector::kMultiNet, &mic_only}.IsAfeWakeWord());
        static_assert(Engine{WakeDetector::kMultiNet, &echo_reference}.IsAfeWakeWord());
        '''
        result = subprocess.run([*compiler, '-std=c++20', '-fsyntax-only', '-x', 'c++', '-'],
                                input=program, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

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
        using esp_err_t = int;
        constexpr bool kRequireWisioPhonemes = REQUIRE_PHONEMES;
        #define ESP_OK 0
        #define ESP_LOGE(...) ((void)0)
        struct Token {
            bool filled = false;
            constexpr bool empty() const { return !filled; }
            constexpr const char* c_str() const { return "HEY WISIO"; }
        };
        struct Command { Token command, phonemes; };
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
            bool fail_alloc = false, fail_add = false, fail_update = false, phonetic = false;
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
            constexpr int esp_mn_commands_phoneme_add(int id, const char* word, const char*) {
                phonetic = true;
                return esp_mn_commands_add(id, word);
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
            if constexpr (kRequireWisioPhonemes) {
                Fixture missing;
                if (missing.initialize() || missing.updated) return false;
                Fixture good;
                good.commands_[0].phonemes.filled = true;
                if (!good.initialize() || !good.phonetic || !good.updated) return false;
                Fixture bad;
                bad.commands_[0].phonemes.filled = true;
                bad.fail_add = true;
                return !bad.initialize() && !bad.updated;
            }
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
            if (rejected.initialize()) return false;
            Fixture explicit_name;
            explicit_name.commands_[0].phonemes.filled = true;
            if (!explicit_name.initialize() || !explicit_name.phonetic) return false;
            Fixture bad_phonemes;
            bad_phonemes.commands_[0].phonemes.filled = true;
            bad_phonemes.fail_add = true;
            return !bad_phonemes.initialize() && !bad_phonemes.updated;
        }
        static_assert(validates_registry_lifecycle());
        '''
        for explicit in [0, 1]:
            result = subprocess.run([*compiler, f'-DREQUIRE_PHONEMES={explicit}', "-std=c++20",
                                     "-fsyntax-only", "-x", "c++", "-"],
                                    input=program, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_return_to_standby_resets_partial_decoder_once(self):
        source = (ROOT / "main/audio/wake_words/custom_wake_word.cc").read_text(encoding="utf-8")
        lifecycle = source[source.index('void CustomWakeWord::Start()'):source.index('void CustomWakeWord::Feed(')]
        program = r'''
        #include <atomic>
        #include <mutex>
        #include <vector>
        #include <cassert>
        #define ESP_LOGI(...) ((void)0)
        struct Model { int resets = 0; void clean(void*) { ++resets; } };
        class CustomWakeWord {
        public:
            void Start(); void Stop();
            std::mutex input_buffer_mutex_;
            Model model;
            Model* multinet_ = &model;
            void* multinet_model_data_ = &model;
            std::atomic<bool> running_{false};
            std::vector<int> input_buffer_{1, 2};
            size_t diagnostic_samples_ = 10;
            int diagnostic_peak_ = 100;
            uint64_t diagnostic_energy_ = 10;
            size_t diagnostic_clipped_ = 0;
            unsigned diagnostic_detections_ = 0, diagnostic_timeouts_ = 0;
        };
        ''' + lifecycle + r'''
        int main() {
            CustomWakeWord wake;
            wake.Start();
            assert(wake.running_ && wake.model.resets == 1 && wake.input_buffer_.empty());
            assert(wake.diagnostic_samples_ == 0 && wake.diagnostic_peak_ == 0);
            wake.input_buffer_.push_back(123);
            wake.Start();
            assert(wake.model.resets == 1 && wake.input_buffer_.size() == 1);
            wake.Stop();
            assert(!wake.running_ && wake.input_buffer_.empty());
            wake.Start();
            assert(wake.model.resets == 2 && wake.running_);
            wake.Stop();
            wake.multinet_model_data_ = nullptr;
            wake.Start();
            assert(!wake.running_ && wake.model.resets == 2);
        }
        '''
        import tempfile
        compiler = json.loads(os.environ.get('WISIO_TEST_CXX', '["g++"]'))
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / 'wake-lifecycle.exe')
            result = subprocess.run([*compiler, '-std=c++20', '-x', 'c++', '-', '-o', binary],
                                    input=program, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([binary], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
