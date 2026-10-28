"""Exercise real speech DSP and delayed software reference with deterministic audio."""
import unittest
import test_protocol_safety as safety

class SpeechWakeDspTests(unittest.TestCase):
    compile_run = safety.ProtocolSafetyTests.compile_run
    def test_speech_boost_is_bounded_odd_symmetric_and_unity_is_exact(self):
        self.compile_run(r'''
#include "../audio/wisio_speech_gain.h"
#include <cassert>
#include <cstdlib>
int main() {
 std::vector<int16_t> pcm{0,1000,-1000,20000,-20000,32767,-32768};
 auto original=pcm;ApplyWisioSpeechGain(pcm,32768);assert(pcm==original);
 ApplyWisioSpeechGain(pcm,58982);
 assert(pcm[0]==0&&pcm[1]==1799&&pcm[2]==-1799);
 assert(pcm[3]>20000&&pcm[3]<30000&&pcm[3]==-pcm[4]);
 for(auto x:pcm) assert(std::abs(int(x))<30000);
 int previous=0;
 for(int x=0;x<=32767;++x){std::vector<int16_t> p{int16_t(x)};
 ApplyWisioSpeechGain(p,58982);assert(p[0]>=previous);previous=p[0];}
}
''')
    def test_reference_follows_echo_delay_wraps_and_clears_after_output_failure(self):
        self.compile_run(r'''
#include "../audio/wisio_playback_reference.h"
#include <cassert>
int main() {
 WisioPlaybackReference ref;
 std::vector<int16_t> source(2400), stereo;
 unsigned seed=42;
 for(auto& x:source){seed=1664525*seed+1013904223;x=int(seed>>16)-32768;}
 ref.Publish(source,1000000);
 std::vector<int16_t> mic(source.begin(),source.begin()+240);
 // Captured echo is delayed 20 ms relative to the default DMA estimate.
 ref.Interleave(mic,1090000,stereo);
 for(int i=0;i<240;++i){assert(stereo[2*i]==mic[i]);assert(stereo[2*i+1]==mic[i]);}
 ref.Clear();ref.Interleave(mic,1100000,stereo);
 for(int i=0;i<240;++i)assert(stereo[2*i+1]==0);
 // Long silence must never repeat old modulo-ring contents.
 ref.Publish(source,3000000);ref.Interleave(mic,2000000,stereo);
 for(int i=0;i<240;++i)assert(stereo[2*i+1]==0);
 for(int n=0;n<20;++n)ref.Publish(source,4000000+n*100000);
 ref.Interleave(mic,1090000,stereo);
 for(int i=0;i<240;++i)assert(stereo[2*i+1]==0);
}
''')

    def test_detected_wake_during_speaking_sends_control_and_reopens_listening(self):
        from test_server_greeting import method_source
        method=method_source((safety.ROOT/'main/application.cc').read_text(encoding='utf-8'),
                             'void Application::HandleWakeWordDetectedEvent(')
        self.compile_run(r'''
#include <atomic>
#include <cassert>
#include <string>
#define ESP_LOGI(...) ((void)0)
enum State {kDeviceStateIdle,kDeviceStateNotifying,kDeviceStateSpeaking,
 kDeviceStateListening,kDeviceStateActivating};
constexpr int kAbortReasonWakeWordDetected=1;
struct Audio {int resets=0;std::string GetLastWakeWord(){return "Hey Wisio";}
 void EnableWakeWordDetection(bool){} void* PopPacketFromSendQueue(){return nullptr;}
 void ResetDecoder(){++resets;}void PlaySound(const char*){}};
struct Peer {int wakes=0;void SendWakeWordDetected(const std::string&){++wakes;}
 void SendStartListening(int){}};
namespace Lang {namespace Sounds {const char* OGG_POPUP="popup";}}
struct Application {
 std::atomic<bool> charging_mode_{false};bool music_playback_=false,play_popup_on_listening_=false;
 Audio audio_service_;Peer peer;Peer* protocol_=&peer;State state=kDeviceStateSpeaking;
 int aborted=0;
 State GetDeviceState(){return state;}void BeginWakeWordInvoke(const std::string&){}
 void StopNotification(){}void AbortSpeaking(int){++aborted;}int GetDefaultListeningMode(){return 0;}
 void SetListeningMode(int){state=kDeviceStateListening;}void SetDeviceState(State s){state=s;}
 void HandleWakeWordDetectedEvent();
};
''' + method + r'''
int main(){Application app;app.HandleWakeWordDetectedEvent();
 assert(app.peer.wakes==1&&app.aborted==1&&app.audio_service_.resets==1);
 assert(app.state==kDeviceStateListening&&app.play_popup_on_listening_);
 app.music_playback_=true;app.HandleWakeWordDetectedEvent();assert(app.peer.wakes==1);
}
''')

if __name__ == '__main__': unittest.main()
