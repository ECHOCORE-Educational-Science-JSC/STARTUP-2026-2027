"""Exercise the actual channel-open branch and state machine for server greetings."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def method_source(source, signature):
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class ServerGreetingTests(unittest.TestCase):
    def test_opt_in_intro_never_opens_microphone_before_real_tts(self):
        compiler = shutil.which("g++") or "C:/Program Files/CodeBlocks/MinGW/bin/g++.exe"
        if not Path(compiler).exists():
            self.skipTest("Host C++ compiler unavailable")
        application = (ROOT / "main/application.cc").read_text(encoding="utf-8")
        method = method_source(application, "void Application::ContinueOpenAudioChannel(")
        wake_method = method_source(application, "void Application::ContinueWakeWordInvoke(")
        stubs = {
            "esp_log.h": "#pragma once\n#define ESP_LOGW(...) ((void)0)\n#define ESP_LOGI(...) ((void)0)\n#define ESP_LOGE(...) ((void)0)\n",
            "cJSON.h": """#pragma once
#include <cstdint>
struct cJSON { int type; const cJSON* pending=nullptr; };
inline const cJSON* cJSON_GetObjectItem(const cJSON* root, const char*) { return root ? root->pending : nullptr; }
inline bool cJSON_IsTrue(const cJSON* item) { return item && item->type==2; }
""",
        }
        harness = r'''
#include <memory>
#include <string>
#include <iostream>
#include <atomic>
#include "esp_log.h"
#include "protocol.h"
#include "device_state_machine.h"
int wake_events=0, wake_audio=0;
#ifndef CONFIG_SEND_WAKE_WORD_DATA
#define CONFIG_SEND_WAKE_WORD_DATA 1
#endif
void Protocol::SendWakeWordDetected(const std::string&) { ++wake_events; }
void Protocol::SendStartListening(ListeningMode) {}
void Protocol::SendStopListening() {}
void Protocol::SendAbortSpeaking(AbortReason) {}
void Protocol::SendMcpMessage(const std::string&) {}
void Protocol::SetError(const std::string&) {}
bool Protocol::IsTimeout() const { return false; }
struct TestProtocol : Protocol {
    bool opened=false, succeeds=true;
    bool Start() override { return true; }
    bool OpenAudioChannel() override { opened=succeeds; return succeeds; }
    void CloseAudioChannel(bool) override { opened=false; }
    bool IsAudioChannelOpened() const override { return opened; }
    bool SendAudio(std::unique_ptr<AudioStreamPacket>) override { ++wake_audio; return true; }
    bool SendText(const std::string&) override { return true; }
    using Protocol::ParseServerGreeting;
    using Protocol::ResetServerGreeting;
};
enum class PowerSaveLevel { PERFORMANCE };
struct Board { static Board& GetInstance() { static Board b; return b; }
    void SetPowerSaveLevel(PowerSaveLevel) {} };
struct TestAudio { bool mic=false, wake=true; int wake_packets=2;
    void EnableVoiceProcessing(bool enabled) { mic=enabled; }
    void EnableWakeWordDetection(bool enabled) { wake=enabled; }
    std::unique_ptr<AudioStreamPacket> PopWakeWordPacket() {
        if(wake_packets-- > 0) return std::make_unique<AudioStreamPacket>();
        return nullptr;
    } };
struct Application {
    std::atomic<bool> charging_mode_{false};
    TestProtocol storage;
    Protocol* protocol_=&storage;
    TestAudio audio_service_;
    DeviceStateMachine machine;
    ListeningMode listening_mode_=kListeningModeManualStop;
    Application() {
        machine.TransitionTo(kDeviceStateStarting);
        machine.TransitionTo(kDeviceStateActivating);
        machine.TransitionTo(kDeviceStateIdle);
        machine.TransitionTo(kDeviceStateConnecting);
        machine.AddStateChangeListener([this](DeviceState, DeviceState to) {
            audio_service_.mic = to==kDeviceStateListening;
        });
    }
    DeviceState GetDeviceState() const { return machine.GetState(); }
    bool SetDeviceState(DeviceState state) { return machine.TransitionTo(state); }
    void SetListeningMode(ListeningMode mode) {
        listening_mode_=mode;
        SetDeviceState(kDeviceStateListening);
    }
    void ContinueOpenAudioChannel(ListeningMode mode);
    void ContinueWakeWordInvoke(const std::string& word);
    ListeningMode GetDefaultListeningMode() const { return kListeningModeAutoStop; }
    bool play_popup_on_listening_=false;
};
''' + method + wake_method + r'''
int main() {
    cJSON yes{2}, no{1}, numeric{8}, text{16};
    cJSON hello{64,&yes};
    Application intro;
    intro.storage.ParseServerGreeting(&hello);
    intro.ContinueOpenAudioChannel(kListeningModeAutoStop);
    if(intro.GetDeviceState()!=kDeviceStateConnecting || intro.audio_service_.mic ||
       intro.audio_service_.wake || intro.listening_mode_!=kListeningModeAutoStop) return 1;
    if(intro.storage.TakeServerGreetingPending()) return 2; // One-shot.
    if(!intro.SetDeviceState(kDeviceStateSpeaking)) return 3; // First actual TTS.
    if(!intro.SetDeviceState(kDeviceStateListening) || !intro.audio_service_.mic) return 4;
    for(const cJSON* absent : {&no,&numeric,&text,static_cast<cJSON*>(nullptr)}) {
        Application legacy;
        hello.pending=absent;
        legacy.storage.ParseServerGreeting(&hello);
        legacy.ContinueOpenAudioChannel(kListeningModeAutoStop);
        if(legacy.GetDeviceState()!=kDeviceStateListening || !legacy.audio_service_.mic) return 5;
    }
    Application reset;
    hello.pending=&yes;
    reset.storage.ParseServerGreeting(&hello);
    reset.storage.ResetServerGreeting();
    if(reset.storage.TakeServerGreetingPending()) return 6;
    Application failure;
    failure.storage.succeeds=false;
    failure.ContinueOpenAudioChannel(kListeningModeAutoStop);
    if(failure.GetDeviceState()!=kDeviceStateIdle || failure.audio_service_.mic) return 7;
    Application fallback;
    fallback.storage.ParseServerGreeting(&hello);
    fallback.ContinueOpenAudioChannel(kListeningModeAutoStop);
    if(!fallback.SetDeviceState(kDeviceStateListening)) return 8; // Bounded bridge fallback.
    Application wake_intro;
    wake_intro.storage.ParseServerGreeting(&hello);
    wake_intro.ContinueWakeWordInvoke("Wisio");
    if(wake_intro.GetDeviceState()!=kDeviceStateConnecting || wake_intro.audio_service_.mic ||
       wake_intro.audio_service_.wake || wake_audio!=0 || wake_events!=0 ||
       wake_intro.audio_service_.wake_packets>0) return 9;
    Application wake_legacy;
    hello.pending=nullptr;
    wake_legacy.storage.ParseServerGreeting(&hello);
    wake_legacy.ContinueWakeWordInvoke("Wisio");
    if(wake_legacy.GetDeviceState()!=kDeviceStateListening || !wake_legacy.audio_service_.mic ||
       wake_audio!=(CONFIG_SEND_WAKE_WORD_DATA ? 2 : 0) || wake_events!=1) return 10;
    return 0;
}
'''
        temporary_root = ROOT / "test-tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="server-greeting-", dir=temporary_root) as directory:
            temporary = Path(directory)
            for name, content in stubs.items():
                (temporary / name).write_text(content, encoding="utf-8")
            (temporary / "test.cc").write_text(harness, encoding="utf-8")
            environment = dict(os.environ)
            environment["PATH"] = str(Path(compiler).parent) + os.pathsep + environment.get("PATH", "")
            executable = temporary / "test.exe"
            for upload in (0, 1):
                with self.subTest(wake_audio_upload=upload):
                    compiled = subprocess.run([
                        compiler, "-std=c++17", f"-DCONFIG_SEND_WAKE_WORD_DATA={upload}",
                        "-I", str(temporary), "-I", str(ROOT / "main"),
                        "-I", str(ROOT / "main/protocols"), str(ROOT / "main/device_state_machine.cc"),
                        str(temporary / "test.cc"), "-o", str(executable),
                    ], env=environment, capture_output=True, text=True)
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    result = subprocess.run([str(executable)], env=environment, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_both_transports_clear_and_parse_the_opt_in(self):
        for transport in ("websocket", "mqtt"):
            source = (ROOT / f"main/protocols/{transport}_protocol.cc").read_text(encoding="utf-8")
            label = "Websocket" if transport == "websocket" else "Mqtt"
            opened = method_source(source, f"bool {label}Protocol::OpenAudioChannel(")
            parsed = method_source(source, f"void {label}Protocol::ParseServerHello(")
            with self.subTest(transport=transport):
                self.assertIn("ResetServerGreeting();", opened)
                self.assertIn("ParseServerGreeting(root);", parsed)


if __name__ == "__main__":
    unittest.main()
