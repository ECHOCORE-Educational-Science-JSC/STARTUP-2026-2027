"""Execute the production Wi-Fi fallback lifecycle with deterministic task/timer events."""
import unittest
import test_music_atomic as atomic
from test_server_greeting import method_source
ROOT = atomic.ROOT

class WifiFallbackTests(unittest.TestCase):
    _compile_run = atomic.AtomicMusicTests._compile_run

    def test_deadlines_reconnect_races_and_explicit_user_guidance(self):
        source = (ROOT / 'main/boards/common/wifi_board.cc').read_text(encoding='utf-8')
        methods = '\n'.join(method_source(source, sig) for sig in (
            'void WifiBoard::TryWifiConnect(', 'void WifiBoard::OnNetworkEvent(',
            'void WifiBoard::ArmWifiConnectTimeout(', 'void WifiBoard::CancelWifiConnectTimeout(',
            'void WifiBoard::OnWifiConnectTimeout(', 'void WifiBoard::StartWifiConfigMode(',
            'void WifiBoard::QueueWifiConfigMode(', 'void WifiBoard::RunWifiConfigTransition(',
            'void WifiBoard::EnterWifiConfigMode('))
        harness = r'''
#include <cassert>
#include <atomic>
#include <string_view>
#include <cstdint>
#include <functional>
#include <mutex>
#include <queue>
#include <string>
#include <vector>
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
#define CONFIG_USE_HOTSPOT_WIFI_PROVISIONING 1
#define CONFIG_LANGUAGE_VI_VN 1
#define ESP_OK 0
#define pdPASS 1
constexpr int CONNECT_TIMEOUT_SEC=12;
int64_t now=100,armed=0;int timer_arms=0,task_creations=0;bool task_failure=false;
int64_t esp_timer_get_time(){return now;}
int esp_timer_start_once(void*,int64_t n){armed=n;++timer_arms;return 0;}
int esp_timer_stop(void*){armed=0;return 0;}
const char* esp_err_to_name(int){return "error";}
std::queue<std::function<void()>> workers;
int xTaskCreate(void(*fn)(void*),const char*,int,void* arg,int,void*){
 ++task_creations;if(task_failure)return 0;workers.push([=](){fn(arg);});return pdPASS;}
void vTaskDelete(void*){}
void run_worker(){assert(!workers.empty());auto job=workers.front();workers.pop();job();}
enum DeviceState{kDeviceStateStarting,kDeviceStateConnecting,kDeviceStateListening,kDeviceStateSpeaking,
 kDeviceStateNotifying,kDeviceStateIdle,kDeviceStateWifiConfiguring,kDeviceStateUpgrading,kDeviceStateFatalError};
enum class NetworkEvent{Connected,Scanning,Connecting,Disconnected,WifiConfigModeEnter,WifiConfigModeExit};
struct Display{std::string message;int setup=0;void ShowWifiSetup(const std::string& s){message=s;++setup;}} display;
struct Application{
 std::queue<std::function<void()>> jobs;int state=kDeviceStateStarting,alerts=0,resets=0;
 std::string alert_message,alert_sound;
 struct Audio{void ResetDecoder(){}} audio;Audio& GetAudioService(){return audio;}
 static Application& GetInstance(){static Application a;return a;}
 void Schedule(std::function<void()> fn){jobs.push(fn);}
 void SetDeviceState(int n){state=n;}int GetDeviceState(){return state;}
 void ResetProtocol(){++resets;}
 void Alert(const char*,const char* hint,const char*,std::string_view sound){
  alert_sound=std::string(sound);++alerts;alert_message=hint;}
 void drain(){while(!jobs.empty()){auto f=jobs.front();jobs.pop();f();}}
};
namespace Lang{namespace Strings{const char* WIFI_CONFIG_MODE="WiFi setup";}namespace Sounds{const char* OGG_WIFICONFIG="offline-wifi-voice";const char* OGG_WIFICONFIG_FAILED="offline-wifi-failed";}}
struct SsidManager{
 std::vector<int> saved{1};static SsidManager& GetInstance(){static SsidManager s;return s;}
 const std::vector<int>& GetSsidList(){return saved;}
};
struct WifiManager{
 bool connected=false,config=false;int starts=0,stops=0,aps=0;
 std::function<void(NetworkEvent)> event;
 static WifiManager& GetInstance(){static WifiManager w;return w;}
 bool IsConnected(){return connected;}bool IsConfigMode(){return config;}
 void StartStation(){++starts;}
 void StopStation(){++stops;connected=false;if(event)event(NetworkEvent::Disconnected);}
 void StartConfigAp(){++aps;config=true;if(event)event(NetworkEvent::WifiConfigModeEnter);}
 std::string GetApSsid(){return "Wisio-1234";}std::string GetApWebUrl(){return "http://192.168.4.1";}
};
struct WifiBoard{
 void* connect_timer_=this;bool in_config_mode_=false;std::mutex wifi_state_mutex_;
 int64_t connect_deadline_us_=0,config_request_deadline_us_=0;bool config_task_pending_=false;
 std::atomic<uint32_t> wifi_config_generation_{0};
 std::function<void(NetworkEvent,const std::string&)> network_event_callback_;
 Display* GetDisplay(){return &display;}
 void TryWifiConnect();void OnNetworkEvent(NetworkEvent,const std::string& data="");
 void ArmWifiConnectTimeout();void CancelWifiConnectTimeout();static void OnWifiConnectTimeout(void*);
 void StartWifiConfigMode();void QueueWifiConfigMode(int64_t expected_deadline_us=0);
 void RunWifiConfigTransition();void EnterWifiConfigMode();
 void StartWifiSetupNotice(std::string_view sound){Application::GetInstance().alert_sound=std::string(sound);}
};
METHODS
void reset(){auto& w=WifiManager::GetInstance();w=WifiManager{};
 auto& a=Application::GetInstance();a=Application{};display=Display{};
 SsidManager::GetInstance().saved={1};workers={};now+=100000000;armed=0;timer_arms=0;task_failure=false;}
int main(){
 reset();{
 WifiBoard b;auto& w=WifiManager::GetInstance();auto& a=Application::GetInstance();
 w.event=[&](NetworkEvent e){b.OnNetworkEvent(e);};
 b.TryWifiConnect();assert(armed==12000000 && w.starts==1);
 const auto initial=b.connect_deadline_us_;
 now+=5000000;b.OnNetworkEvent(NetworkEvent::Disconnected);b.OnNetworkEvent(NetworkEvent::Scanning);
 assert(b.connect_deadline_us_==initial && timer_arms==1);
 now=initial-1;b.OnWifiConnectTimeout(&b);assert(workers.empty());
 now=initial;b.OnWifiConnectTimeout(&b);b.OnWifiConnectTimeout(&b);assert(workers.size()==1);
 assert(w.aps==0 && display.setup==0); // Timer does no blocking network or UI work.
 run_worker();assert(w.aps==1 && w.stops==1 && b.connect_deadline_us_==0);
 assert(display.setup==0);a.drain();assert(a.alerts==1 && a.alert_sound=="offline-wifi-failed" && a.state==kDeviceStateWifiConfiguring);
 assert(display.message.find("Không kết nối được Wi-Fi")!=std::string::npos);
 assert(display.message.find("Wisio-1234")!=std::string::npos && display.message.find("192.168.4.1")!=std::string::npos);
 b.OnNetworkEvent(NetworkEvent::Disconnected);assert(armed==0);
 w.config=false;b.OnNetworkEvent(NetworkEvent::WifiConfigModeExit);a.drain();assert(armed==12000000 && w.starts==2);
 w.connected=true;b.OnNetworkEvent(NetworkEvent::Connected,"saved");assert(armed==0);
 now+=1000000;w.connected=false;b.OnNetworkEvent(NetworkEvent::Disconnected);assert(armed==12000000);
 }
 reset();{ // A got-IP event cancels a timeout already queued on a worker.
 WifiBoard b;auto& w=WifiManager::GetInstance();b.TryWifiConnect();now=b.connect_deadline_us_;
 b.OnWifiConnectTimeout(&b);w.connected=true;b.OnNetworkEvent(NetworkEvent::Connected);
 run_worker();assert(w.aps==0 && !b.config_task_pending_);
 }
 reset();{ // A stale callback must not shorten a later reconnect attempt.
 WifiBoard b;b.TryWifiConnect();now=b.connect_deadline_us_;b.OnWifiConnectTimeout(&b);
 b.CancelWifiConnectTimeout();now+=100;b.ArmWifiConnectTimeout();auto fresh=b.connect_deadline_us_;
 run_worker();assert(WifiManager::GetInstance().aps==0 && b.connect_deadline_us_==fresh);
 }
 reset();{ // A new device opens setup immediately and tells the user what to do.
 SsidManager::GetInstance().saved.clear();WifiBoard b;b.TryWifiConnect();assert(workers.size()==1 && timer_arms==0);
 run_worker();Application::GetInstance().drain();assert(Application::GetInstance().alerts==1 && Application::GetInstance().alert_sound=="offline-wifi-voice");
 }
 reset();{ // Manual setup works from a live conversation, through idle.
 WifiBoard b;auto& a=Application::GetInstance();a.state=kDeviceStateSpeaking;
 b.EnterWifiConfigMode();b.EnterWifiConfigMode();assert(workers.size()==1);
 run_worker();a.drain();assert(a.resets==1 && a.state==kDeviceStateWifiConfiguring);
 }
 reset();{ // Failed allocation cannot leave a permanently pending transition.
 WifiBoard b;b.TryWifiConnect();now=b.connect_deadline_us_;task_failure=true;b.OnWifiConnectTimeout(&b);
 assert(!b.config_task_pending_ && armed==1000000);task_failure=false;
 now+=1000000;b.OnWifiConnectTimeout(&b);run_worker();assert(WifiManager::GetInstance().aps==1);
 }
 reset();{ // The old hint must not overwrite a newly accepted Wi-Fi config.
 WifiBoard b;b.StartWifiConfigMode();run_worker();WifiManager::GetInstance().config=false;
 Application::GetInstance().drain();assert(Application::GetInstance().alerts==0);
 }
 return 0;
}
'''
        self._compile_run(harness.replace('METHODS', methods))

    def test_cancelled_notice_cannot_enqueue_audio_after_setup_exits(self):
        source=(ROOT/'main/audio/audio_service.cc').read_text(encoding='utf-8')
        methods='\n'.join(method_source(source,sig) for sig in (
            'bool AudioService::PushPacketToDecodeQueue(', 'void AudioService::PlaySound('))
        self._compile_run(r'''
#include <cassert>
#include <atomic>
#include <condition_variable>
#include <cstring>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <string_view>
#include <vector>
#include "audio/music_playback_clock.h"
#include "protocols/audio_packet.h"
constexpr int MAX_DECODE_PACKETS_IN_QUEUE=20,AUDIO_POWER_CHECK_INTERVAL_MS=1000;
void esp_timer_stop(void*){}void esp_timer_start_periodic(void*,int){}
struct AudioStreamPacket{int sample_rate=16000,frame_duration=60;uint32_t playback_id=0,music_epoch=0;std::vector<uint8_t> payload;};
struct Codec{bool enabled=false;bool output_enabled(){return enabled;}void EnableOutput(bool on){enabled=on;}};
struct OggDemuxer{
 std::function<void(const uint8_t*,int,int,size_t)> cb;
 void OnPacket(decltype(cb) f){cb=f;}void Reset(){}
 void Process(const uint8_t*,size_t){uint8_t b=0;for(int i=0;i<3;++i)cb(&b,16000,60,1);}
};
struct AudioService{
 std::mutex audio_queue_mutex_,output_power_mutex_;std::condition_variable audio_queue_cv_;
 std::atomic<bool> service_stopped_{false},suspended_{false};uint32_t playback_generation_=0;
 bool playback_drained_notified_=true;MusicPlaybackClock music_clock_;
 std::deque<std::unique_ptr<AudioStreamPacket>> audio_decode_queue_;
 Codec storage;Codec* codec_=&storage;void* audio_power_timer_=nullptr;
 bool PushPacketToDecodeQueue(std::unique_ptr<AudioStreamPacket>,bool wait=false,const std::function<bool()>& accept={});
 void PlaySound(const std::string_view&,std::function<bool()> keep={});
};
METHODS
int main(){
 AudioService a;a.PlaySound("ogg");assert(a.audio_decode_queue_.size()==3);
 AudioService b;int checks=0;b.PlaySound("ogg",[&](){return ++checks<3;});
 assert(b.audio_decode_queue_.empty()); // Cancellation between demux and queue admission.
 AudioService muted;muted.PlaySound("ogg",[](){return false;});assert(!muted.storage.enabled);
 AudioService c;auto epoch=c.music_clock_.Start(16000);
 auto p=std::make_unique<AudioStreamPacket>();p->payload={0};p->playback_id=7;
 assert(c.PushPacketToDecodeQueue(std::move(p)) && c.audio_decode_queue_.back()->music_epoch==0);
 auto speech=std::make_unique<AudioStreamPacket>();speech->payload={0};
 assert(c.PushPacketToDecodeQueue(std::move(speech)) && c.audio_decode_queue_.back()->music_epoch==epoch);
}
'''.replace('METHODS',methods))

    def test_setup_text_has_every_glyph_in_the_offline_builtin_font(self):
        import re
        font=(ROOT/'managed_components/78__xiaozhi-fonts/src/font_noto_sans_basic_20_4.c').read_text(encoding='utf-8')
        ranges=re.search(r' -r ([0-9a-fx,-]+)',font)[1]
        supported=set()
        for part in ranges.split(','):
            ends=[int(n,16) for n in part.split('-')]
            supported.update(range(ends[0],ends[-1]+1))
        source=(ROOT/'main/boards/common/wifi_board.cc').read_text(encoding='utf-8')
        words=re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"',source)
        actual={ord(c) for text in words for c in text if ord(c)>127}
        self.assertTrue(actual)
        self.assertFalse(actual-supported, 'Setup needs unsupported offline glyphs: '+str(actual-supported))

    def test_offline_failure_notice_is_present_and_build_orders_its_generated_symbol(self):
        sound=ROOT/'main/assets/locales/vi-VN/wificonfig_failed.ogg'
        self.assertTrue(sound.read_bytes().startswith(b'OggS'))
        self.assertIn(b'OpusHead', sound.read_bytes())
        cmake=(ROOT/'main/CMakeLists.txt').read_text(encoding='utf-8')
        dependencies=cmake.split('OUTPUT ${LANG_HEADER}',1)[-1]
        self.assertIn('${LANG_SOUNDS}', dependencies)
        self.assertIn('add_dependencies(${COMPONENT_LIB} lang_header)',cmake)

    def test_wifi_setup_is_visible_above_startup_and_keeps_vietnamese_font(self):
        source=(ROOT/'main/boards/freenove-esp32s3-display-2.8-lcd/freenove-esp32s3-display-2.8-lcd.cc').read_text(encoding='utf-8')
        method=method_source(source,'    void ShowWifiSetup(')
        method=method.replace(' override','')
        self._compile_run(r'''
#include <cassert>
#include <string>
#include <cstdint>
struct Obj{std::string text;int width=0,z=0;const void* font=nullptr;};
using lv_obj_t=Obj;int BUILTIN_TEXT_FONT=1,layers=0,panels=0;
constexpr int LV_LABEL_LONG_WRAP=1;
Obj* lv_screen_active(){return nullptr;}Obj* lv_label_create(Obj*){return new Obj;}
void lv_obj_set_width(Obj* o,int n){o->width=n;}
void lv_obj_set_style_text_font(Obj* o,const void* p,int){o->font=p;}
void lv_obj_set_style_text_color(Obj*,int,int){}int lv_color_hex(int n){return n;}
void lv_label_set_long_mode(Obj*,int){}void lv_obj_center(Obj*){}
void lv_label_set_text(Obj* o,const char* s){o->text=s;}
void lv_obj_move_foreground(Obj* o){o->z=++layers;}
struct DisplayLockGuard{template<class T>DisplayLockGuard(T*){}};
struct EchoCoreLcdDisplay{int width_=320,height_=240,music_stops=0;
 Obj* wifi_setup_panel_=nullptr;Obj* wifi_setup_message_=nullptr;
 void HideMusicPlayer(){++music_stops;}
 Obj* MakeBlock(Obj*,int,int,int,int,int,int){++panels;return new Obj;}
 METHOD
};
int main(){EchoCoreLcdDisplay d;d.ShowWifiSetup("Không kết nối được Wi-Fi");
 assert(d.wifi_setup_message_->text=="Không kết nối được Wi-Fi" && panels==1);
 assert(d.wifi_setup_message_->font==&BUILTIN_TEXT_FONT && d.wifi_setup_message_->width==296);
 auto* panel=d.wifi_setup_panel_;d.ShowWifiSetup("Wisio-1234\nhttp://192.168.4.1");
 assert(d.wifi_setup_panel_==panel && panels==1 && d.music_stops==2 && panel->z==2);
}
'''.replace('METHOD',method))
        animation=method_source(source,'    void AnimateWaiting(')
        self.assertLess(animation.index('wifi_setup_panel_'), animation.index('if (splash_ == nullptr)'))

if __name__=='__main__': unittest.main()
