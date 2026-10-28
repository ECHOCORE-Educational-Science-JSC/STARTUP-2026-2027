"""Run the production music clock, output task and progress callback on the host."""
import unittest
import test_music_atomic as atomic
from test_server_greeting import method_source

ROOT = atomic.ROOT


class MusicClockTests(unittest.TestCase):
    _compile_run = atomic.AtomicMusicTests._compile_run

    def test_sample_rates_stalls_track_changes_and_saturation(self):
        self._compile_run(r'''
#include <cassert>
#include "audio/music_playback_clock.h"
int main(){
 MusicPlaybackClock c;
 for(auto rate:{16000u,24000u,48000u}){
  auto epoch=c.Start(rate);
  assert(c.PositionMs()==0);
  for(int n=0;n<500;++n)c.Written(epoch,rate/100);
  assert(c.PositionMs()==5000); // No wall clock or server position can advance it.
  c.Written(0,rate);assert(c.PositionMs()==5000);
  auto next=c.Start(rate);
  c.Written(epoch,rate*60);assert(c.PositionMs()==0);
  c.Written(next,rate);assert(c.PositionMs()==1000);
  c.Stop();c.Written(next,rate);assert(c.PositionMs()==0);
 }
 auto epoch=c.Start(48000);
 c.Written(epoch,static_cast<size_t>(UINT32_MAX)*48000);
 assert(c.PositionMs()>=UINT32_MAX-1);
 auto saturated=c.PositionMs();c.Written(epoch,48000);assert(c.PositionMs()==saturated);
 c.Start(0);c.Written(c.epoch(),48000);assert(c.PositionMs()==0);
}
''')

    def test_real_output_task_counts_only_successful_current_music_writes(self):
        source = (ROOT / 'main/audio/audio_service.cc').read_text(encoding='utf-8')
        method = method_source(source, 'void AudioService::AudioOutputTask(')
        self._compile_run(r'''
#include <cassert>
#include <atomic>
#include <condition_variable>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <vector>
#include "audio/music_playback_clock.h"
#include "audio/wisio_speech_gain.h"
#define ESP_LOGW(...) ((void)0)
#define CONFIG_USE_SERVER_AEC 0
constexpr int AUDIO_POWER_CHECK_INTERVAL_MS=1000;
void esp_timer_stop(void*){} void esp_timer_start_periodic(void*,int){}
int64_t esp_timer_get_time(){return 123000;}
struct Codec {
 bool success=true;std::atomic<bool>* stopped=nullptr;int last=0;
 int speech_gain_q15(){return 58982;}
 bool output_enabled(){return true;}void EnableOutput(bool){}
 bool OutputData(std::vector<int16_t>& pcm){last=pcm[0];stopped->store(true);return success;}
};
struct AudioTask {std::vector<int16_t> pcm;uint32_t music_epoch=0,playback_id=0,media_position_ms=0;};
struct AudioService {
 std::mutex audio_queue_mutex_,output_power_mutex_;std::condition_variable audio_queue_cv_;
 std::atomic<bool> service_stopped_{false},suspended_{false};std::atomic<uint32_t> last_output_time_ms_{0};
 std::deque<std::unique_ptr<AudioTask>> audio_playback_queue_;bool output_in_flight_=false;
 Codec storage;Codec* codec_=&storage;void* audio_power_timer_=nullptr;MusicPlaybackClock music_clock_;
 struct {int playback_count=0;} debug_statistics_;
 struct {std::function<void(uint32_t,uint32_t)> on_playback_progress;
         std::function<void()> on_playback_drained;} callbacks_;
 bool MarkPlaybackDrainedLocked(){return true;}
 void AudioOutputTask();
};
''' + method + r'''
int main(){
 for(int mode=0;mode<4;++mode){
  AudioService a;a.storage.stopped=&a.service_stopped_;
  auto old=a.music_clock_.Start(16000);auto epoch=a.music_clock_.Start(16000);
  auto task=std::make_unique<AudioTask>();task->pcm.resize(960,1000);
  task->music_epoch=mode==2?old:mode==3?0:epoch;
  a.storage.success=mode!=1;a.audio_playback_queue_.push_back(std::move(task));
  a.AudioOutputTask();
  assert(a.music_clock_.PositionMs()==(mode==0?60:0));
  assert(a.storage.last==(mode==3?1799:1000));
  assert(!a.output_in_flight_ && a.audio_playback_queue_.empty());
 }
}
''')

    def test_actual_progress_callback_ignores_server_lead_and_stale_tokens(self):
        source = (ROOT / 'main/application.cc').read_text(encoding='utf-8')
        block = source.split('music_state == MusicMessageState::kProgress', 1)[1].split(
            'music_state == MusicMessageState::kStop', 1)[0]
        callback = method_source(block, 'Schedule(')
        body = callback[callback.index('{'):]
        self._compile_run(r'''
#include <cassert>
#include <cstdint>
#include <string>
struct Display{uint32_t position=0,duration=0;int updates=0;
 void UpdateMusicProgress(uint32_t p,uint32_t d){position=p;duration=d;++updates;}};
struct Audio{uint32_t MusicPlaybackPositionMs(){return 5000;}};
struct Application{
 std::string music_playback_token_="current";uint32_t music_duration_ms_=278000;Audio audio_service_;
 void Progress(Display* display,std::string token,uint32_t duration_ms,uint32_t server_position)
 BODY
};
int main(){Application a;Display d;
 a.Progress(&d,"current",278000,220000);
 assert(d.position==5000 && d.duration==278000 && d.updates==1);
 a.Progress(&d,"old",10000,9000);assert(d.updates==1 && a.music_duration_ms_==278000);
 a.Progress(&d,"current",0,250000);assert(d.position==5000 && d.duration==278000);
}
'''.replace('BODY', body))


if __name__ == '__main__':
    unittest.main()
