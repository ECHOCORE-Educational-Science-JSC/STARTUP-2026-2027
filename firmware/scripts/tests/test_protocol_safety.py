"""Compile production receive/handshake code against hostile network inputs."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_server_greeting import method_source

ROOT = Path(__file__).resolve().parents[2]


class ProtocolSafetyTests(unittest.TestCase):
    def compile_run(self, harness):
        compiler = shutil.which("g++") or "C:/Program Files/CodeBlocks/MinGW/bin/g++.exe"
        if not Path(compiler).exists():
            self.skipTest("Host C++ compiler unavailable")
        with tempfile.TemporaryDirectory(dir=ROOT / "test-tmp", prefix="protocol-safety-") as folder:
            folder = Path(folder)
            (folder / "cJSON.h").write_text(r'''
#pragma once
#include <cstring>
struct cJSON { const char* valuestring=nullptr; int valueint=0; double valuedouble=0;
 int type=0; const cJSON* child=nullptr; const cJSON* next=nullptr; const char* key=""; };
inline const cJSON* cJSON_GetObjectItem(const cJSON* root,const char* key) {
 for(auto p=root?root->child:nullptr;p;p=p->next) if(!strcmp(p->key,key)) return p;
 return nullptr;
}
inline bool cJSON_IsString(const cJSON* p) {return p && p->type==1 && p->valuestring;}
inline bool cJSON_IsObject(const cJSON* p) {return p && p->type==2;}
inline bool cJSON_IsNumber(const cJSON* p) {return p && p->type==3;}
inline bool cJSON_IsTrue(const cJSON* p) {return p && p->type==4;}
inline cJSON* cJSON_ParseWithLength(const char*,size_t) {return nullptr;}
inline void cJSON_Delete(const cJSON*) {}
''', encoding="utf-8")
            (folder / "test.cc").write_text(harness, encoding="utf-8")
            environment = dict(os.environ)
            environment["PATH"] = str(Path(compiler).parent) + os.pathsep + environment.get("PATH", "")
            executable = folder / "test.exe"
            result = subprocess.run([compiler, "-std=c++17", "-I", str(folder), "-I",
                str(ROOT / "main/protocols"), str(folder / "test.cc"), "-o", str(executable)],
                env=environment, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(executable)], env=environment, capture_output=True,
                                    text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

    def test_real_websocket_callback_rejects_truncation_without_mutating_input(self):
        source = (ROOT / "main/protocols/websocket_protocol.cc").read_text(encoding="utf-8")
        callback = method_source(source, "websocket_->OnData(")
        body = callback[callback.index("{")+1:-1]
        self.compile_run(r'''
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cassert>
#include <cstring>
#include "protocol.h"
#if __has_include("audio_packet.h")
#include "audio_packet.h"
#endif
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
uint16_t ntohs(uint16_t n){return (n>>8)|(n<<8);}
uint32_t ntohl(uint32_t n){return ((uint32_t)ntohs(n)<<16)|ntohs(n>>16);}
struct Receiver {
 int version_=2, server_sample_rate_=24000, server_frame_duration_=60, calls=0;
 std::atomic<uint32_t> connection_generation_{0};
 std::chrono::steady_clock::time_point last_incoming_time_;
 std::function<void(const cJSON*)> on_incoming_json_;
 std::function<void(std::unique_ptr<AudioStreamPacket>)> on_incoming_audio_;
 std::unique_ptr<AudioStreamPacket> received;
 Receiver(){on_incoming_audio_=[this](auto packet){++calls; received=std::move(packet);};}
 void ParseServerHello(const cJSON*){}
 void Receive(const char* data,size_t len,bool binary=true){
 const uint32_t generation=0;
''' + body + r'''
 }
};
int main(){
 SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
 Receiver r;
 static const char v2[]="\0\2\0\0\0\0\0\0\0\0\1\2\0\0\0\3abc";
 r.Receive(v2,19);
 assert(r.calls==1 && r.received->timestamp==258 && r.received->payload.size()==3);
 for(size_t i=0;i<19;++i) r.Receive(v2,i);
 assert(r.calls==1);
 std::string bad(v2,19); bad[15]=4; r.Receive(bad.data(),bad.size());
 bad.assign(v2,19); bad[1]=3; r.Receive(bad.data(),bad.size());
 bad.assign(v2,19); bad[3]=1; r.Receive(bad.data(),bad.size());
 bad.assign(v2,19); memset(bad.data()+12,255,4); r.Receive(bad.data(),bad.size());
 assert(r.calls==1);
 r.version_=3;
 static const char v3[]="\0\0\0\3abc";
 r.Receive(v3,7); assert(r.calls==2 && r.received->timestamp==0);
 for(size_t i=0;i<7;++i) r.Receive(v3,i);
 assert(r.calls==2);
 r.version_=1; r.Receive(nullptr,0); r.Receive("abc",3);
 assert(r.calls==3);
 std::string oversized(8193,'a'); r.Receive(oversized.data(),oversized.size());
 r.version_=42; r.Receive("abc",3); assert(r.calls==3);
 return 0;
}
''')

    def test_handshake_rejects_bad_audio_and_missing_transport(self):
        protocol = (ROOT / "main/protocols/protocol.cc").read_text(encoding="utf-8")
        websocket = (ROOT / "main/protocols/websocket_protocol.cc").read_text(encoding="utf-8")
        validator = method_source(protocol, "bool Protocol::ParseServerAudioParameters(")
        hello = method_source(websocket, "void WebsocketProtocol::ParseServerHello(")
        self.compile_run(r'''
#include <cassert>
#include "cJSON.h"
#include "audio_packet.h"
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
#define WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT 1
int signalled=0;
void xEventGroupSetBits(int,int){++signalled;}
struct Protocol {static bool ParseServerAudioParameters(const cJSON*,int&,int&);};
struct WebsocketProtocol:Protocol {
 int server_sample_rate_=24000,server_frame_duration_=60,event_group_handle_=0;
 std::string session_id_;
 bool greeting=false;
 void ParseServerGreeting(const cJSON*){greeting=true;}
 void ParseServerHello(const cJSON*);
};
''' .replace('#include <cassert>', '#include <cassert>\n#include <string>') + validator + hello + r'''
int main(){
 WebsocketProtocol p;
 cJSON root; root.type=2;
 p.ParseServerHello(&root); assert(signalled==0);
 cJSON transport; transport.type=1;transport.valuestring="websocket";transport.key="transport";
 root.child=&transport;
 p.ParseServerHello(&root); assert(signalled==1);
 cJSON params;params.type=2;params.key="audio_params";transport.next=&params;
 cJSON rate;rate.type=3;rate.valueint=16000;rate.valuedouble=16000;rate.key="sample_rate";
 params.child=&rate;
 p.ParseServerHello(&root);assert(signalled==2 && p.server_sample_rate_==16000);
 for(double bad:{-1.0,0.0,44100.0,24000.5,1e30}){
  rate.valuedouble=bad; rate.valueint=bad<1e20?int(bad):2147483647;
  p.ParseServerHello(&root); assert(signalled==2 && p.server_sample_rate_==16000);
 }
 rate.valuedouble=24000;rate.valueint=24000;
 cJSON duration;duration.type=3;duration.key="frame_duration";rate.next=&duration;
 for(int invalid:{-100,0,1,7,1000000}){
  duration.valueint=invalid;duration.valuedouble=invalid;p.ParseServerHello(&root);assert(signalled==2);
 }
 duration.valueint=60;duration.valuedouble=60;
 cJSON channels;channels.type=3;channels.key="channels";channels.valuedouble=2;duration.next=&channels;
 p.ParseServerHello(&root);assert(signalled==2);
 channels.valuedouble=1;p.ParseServerHello(&root);assert(signalled==3);
 return 0;
}
''')

    def test_endpoint_parser_rejects_invalid_and_overflowing_ports(self):
        self.compile_run(r'''
#include <cassert>
#include "network_endpoint.h"
int main(){
 std::string host;int port;
 assert(network_endpoint::Parse("broker.example",host,port)&&host=="broker.example"&&port==8883);
 assert(network_endpoint::Parse("broker.example:1883",host,port)&&port==1883);
 assert(network_endpoint::Parse("[::1]:8883",host,port)&&host=="::1");
 assert(network_endpoint::Parse("2001:db8::1",host,port)&&host=="2001:db8::1");
 for(const char* bad:{"",":8883","host:","host:no","host:-1","host:65536","host:0",
    "host:99999999999999999999999","[::1","[]:4","host/path","host:12x","host name"})
  assert(!network_endpoint::Parse(bad,host,port));
 return 0;
}
''')

    def test_real_udp_callback_rejects_bad_length_type_and_replayed_audio(self):
        source = (ROOT / "main/protocols/mqtt_protocol.cc").read_text(encoding="utf-8")
        callback = method_source(source, "udp->OnMessage([this]")
        body = callback[callback.index("{")+1:-1]
        self.compile_run(r'''
#include <cassert>
#include <mutex>
#include "protocol.h"
#include "audio_packet.h"
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
uint16_t ntohs(uint16_t n){return (n>>8)|(n<<8);}
uint32_t ntohl(uint32_t n){return ((uint32_t)ntohs(n)<<16)|ntohs(n>>16);}
struct Receiver {
 int server_sample_rate_=24000,server_frame_duration_=60,calls=0;
 std::chrono::steady_clock::time_point last_incoming_time_;
 std::mutex channel_mutex_;uint32_t remote_sequence_=0;
 std::function<void(std::unique_ptr<AudioStreamPacket>)> on_incoming_audio_;
 Receiver(){on_incoming_audio_=[this](auto p){assert(p->payload.size()==3);++calls;};}
 bool CryptAesCtr(const uint8_t* data,size_t length,const uint8_t*,uint8_t* out){memcpy(out,data,length);return true;}
 void Receive(const std::string& data){
''' + body + r'''
 }
};
int main(){
 Receiver r;
 std::string packet(19,'\0');packet[0]=1;packet[3]=3;packet[15]=1;
 for(size_t i=0;i<packet.size();++i)r.Receive(packet.substr(0,i));
 assert(r.calls==0);r.Receive(packet);assert(r.calls==1);
 r.Receive(packet);assert(r.calls==1);
 packet[15]=2;packet[0]=2;r.Receive(packet);assert(r.calls==1);
 packet[0]=1;packet[3]=4;r.Receive(packet);assert(r.calls==1);
 packet.resize(16+8193);packet[2]=32;packet[3]=1;r.Receive(packet);assert(r.calls==1);
 packet.resize(19);packet[2]=0;packet[3]=3;r.Receive(packet);assert(r.calls==2);
 return 0;
}
''')

    def test_outgoing_control_messages_escape_session_and_wake_text(self):
        source = (ROOT / 'main/protocols/protocol.cc').read_text(encoding='utf-8')
        methods = ''.join(method_source(source, sig).replace('Protocol::', 'Sender::') for sig in (
            'void Protocol::SendAbortSpeaking(', 'void Protocol::SendWakeWordDetected(',
            'void Protocol::SendStartListening(', 'void Protocol::SendStopListening(',
            'void Protocol::SendMcpMessage('))
        output = self.compile_run(r'''
#include <iostream>
#include "protocol.h"
#include "protocol_json.h"
struct Sender {
 std::string session_id_="session\"\\\n";
 void SendAbortSpeaking(AbortReason);void SendWakeWordDetected(const std::string&);
 void SendStartListening(ListeningMode);void SendStopListening();void SendMcpMessage(const std::string&);
 bool SendText(const std::string& s){std::cout<<s<<'\n';return true;}
};
''' + methods + r'''
int main(){
 Sender s;s.SendAbortSpeaking(kAbortReasonWakeWordDetected);s.SendWakeWordDetected("hey \"Wisio\"\n");
 s.SendStartListening(kListeningModeAutoStop);s.SendStopListening();s.SendMcpMessage("{\"id\":1}");
}
''')
        messages = [json.loads(line) for line in output.splitlines()]
        self.assertEqual(len(messages), 5)
        self.assertTrue(all(message['session_id'] == 'session"\\\n' for message in messages))
        self.assertEqual(messages[1]['text'], 'hey "Wisio"\n')
        self.assertEqual(messages[-1]['payload'], {'id': 1})

    def test_old_socket_close_does_not_cancel_a_reconnected_conversation(self):
        source = (ROOT / 'main/protocols/websocket_protocol.cc').read_text(encoding='utf-8')
        callback = method_source(source, 'websocket_->OnDisconnected(')
        body = callback[callback.index('{')+1:-1]
        application = (ROOT / 'main/application.cc').read_text(encoding='utf-8')
        callback = method_source(application, 'protocol_->OnAudioChannelClosed(')
        app_body = callback[callback.index('{')+1:-1]
        self.compile_run(r'''
#include <cassert>
#include <atomic>
#include <functional>
#include <vector>
#define ESP_LOGI(...) ((void)0)
struct Socket {
 std::atomic<uint32_t> connection_generation_{2};int calls=0;
 std::function<void()> on_audio_channel_closed_=[this]{++calls;};
 void Closed(uint32_t generation){
''' + body + r'''
 }
};
enum class PowerSaveLevel{LOW_POWER};
constexpr int kDeviceStateIdle=0;
struct Display{void SetChatMessage(const char*,const char*){}};
struct Board{Display display;int low_power=0;
 static Board& GetInstance(){static Board b;return b;}
 Display* GetDisplay(){return &display;}
 void SetPowerSaveLevel(PowerSaveLevel){++low_power;}
};
struct Protocol {bool opened=false;bool IsAudioChannelOpened(){return opened;}};
struct Application{
 Protocol storage;Protocol* protocol_=&storage;int idle=0;
 std::vector<std::function<void()>> jobs;
 void Schedule(std::function<void()> f){jobs.push_back(f);}
 void SetDeviceState(int){++idle;}
 void Closed(){
''' + app_body + r'''
 }
};
int main(){
 Socket s;s.Closed(1);assert(s.calls==0);s.Closed(2);assert(s.calls==1);
 Application a;a.Closed();a.storage.opened=true;a.jobs[0]();
 assert(a.idle==0&&Board::GetInstance().low_power==0);
 a.jobs.clear();a.Closed();a.storage.opened=false;a.jobs[0]();
 assert(a.idle==1&&Board::GetInstance().low_power==1);
 return 0;
}
''')

    def test_touch_read_failure_cannot_trigger_wifi_reset_or_chat_toggle(self):
        source = (ROOT / 'main/boards/freenove-esp32s3-display-2.8-lcd/freenove-esp32s3-display-2.8-lcd.cc').read_text(encoding='utf-8')
        method = method_source(source, 'static void TouchTask(')
        self.compile_run(r'''
#include <cassert>
#include <cstdint>
#include <vector>
#define pdMS_TO_TICKS(x) (x)
constexpr int kDeviceStateStarting=1,kDeviceStateActivating=2,kDeviceStateWifiConfiguring=3;
struct Stop{};
struct Sample{bool ok,touched;uint32_t time;};
std::vector<Sample> events{{true,true,5000},{false,false,9001},{true,false,9051},
                         {true,true,10000},{true,false,10100}};
size_t cursor=0;uint64_t now=0;
uint64_t esp_timer_get_time(){return now*1000;}
void vTaskDelay(int){if(cursor==events.size())throw Stop{};}
struct Application {
 int toggles=0;static Application& GetInstance(){static Application a;return a;}
 bool IsChargingMode(){return false;}int GetDeviceState(){return 0;}
 void StartListening(){++toggles;}void ToggleChatState(){++toggles;}
};
struct Touch{
 bool Read(bool& touched,uint16_t&,uint16_t&){auto e=events.at(cursor++);now=e.time;touched=e.touched;return e.ok;}
};
struct FreenoveESP32S3Display{
 Touch touch_;int wifi_resets=0;void EnterWifiConfigMode(){++wifi_resets;}
''' + method + r'''
};
int main(){
 FreenoveESP32S3Display board;
 try{board.TouchTask(&board);}catch(const Stop&){}
 assert(board.wifi_resets==0&&Application::GetInstance().toggles==1);
 return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
