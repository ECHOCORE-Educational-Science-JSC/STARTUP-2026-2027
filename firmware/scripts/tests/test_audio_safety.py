"""Failure injection for the production decoder, audio timer and codec I/O."""
import unittest
import test_protocol_safety as protocol_tests

ROOT = protocol_tests.ROOT
from test_server_greeting import method_source


class AudioSafetyTests(unittest.TestCase):
    compile_run = protocol_tests.ProtocolSafetyTests.compile_run
    def test_mute_survives_restart_and_failed_volume_update_does_not_persist(self):
        base = (ROOT / "main/audio/audio_codec.cc").read_text(encoding="utf-8")
        codec = (ROOT / "main/audio/codecs/es8311_audio_codec.cc").read_text(encoding="utf-8")
        methods = ''.join(method_source(base, sig) for sig in (
            'void AudioCodec::Start(', 'void AudioCodec::SetOutputVolume(', 'bool AudioCodec::InputData(',
            'bool AudioCodec::OutputData('))
        methods += method_source(codec, 'void Es8311AudioCodec::SetOutputVolume(')
        self.compile_run(r'''
#include <cassert>
#include <vector>
#include <mutex>
#include <algorithm>
#include <cstdint>
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_OK 0
int stored=0,persisted=-1,error=0,hardware=-1;
struct Settings {Settings(const char*,bool){} int GetInt(const char*,int){return stored;}
 void SetInt(const char*,int n){persisted=n;}};
int esp_codec_dev_set_out_vol(void*,int n){hardware=n;return error;}
struct AudioCodec {
 int output_volume_=70,read_result=0;
 void Start();void SetOutputVolume(int);bool InputData(std::vector<int16_t>&);bool OutputData(std::vector<int16_t>&);
 int Read(int16_t*,int){return read_result;}
 int Write(const int16_t*,int){return read_result;}
};
struct Es8311AudioCodec:AudioCodec {
 void* dev_=this;int output_volume_limit_=100;std::mutex data_if_mutex_;void SetOutputVolume(int);
};
''' + methods + r'''
int main(){
 Es8311AudioCodec a;a.Start();assert(a.output_volume_==0);
 stored=999;a.Start();assert(a.output_volume_==100);
 a.SetOutputVolume(-42);assert(hardware==0&&persisted==0&&a.output_volume_==0);
 a.output_volume_limit_=85;a.SetOutputVolume(100);
 assert(hardware==85&&persisted==100&&a.output_volume_==100);
 a.SetOutputVolume(50);assert(hardware==42&&persisted==50);
 a.SetOutputVolume(0);assert(hardware==0&&persisted==0);
 error=-1;a.SetOutputVolume(70);assert(persisted==0&&a.output_volume_==0);
 std::vector<int16_t> pcm(320);a.read_result=319;assert(!a.InputData(pcm));
 assert(!a.OutputData(pcm));
 a.read_result=320;assert(a.InputData(pcm));
 assert(a.OutputData(pcm));
 return 0;
}
''')

    def test_failed_resampling_never_plays_unconverted_or_uninitialized_samples(self):
        source = (ROOT / 'main/audio/audio_service.cc').read_text(encoding='utf-8')
        method = method_source(source, 'bool AudioService::ConvertOutputFrame(')
        self.compile_run(r'''
#include <cassert>
#include <vector>
#include <cstdint>
#define ESP_AE_ERR_OK 0
using esp_ae_sample_t=void*;
int fail=0;
int esp_ae_rate_cvt_get_max_out_sample_num(void*,uint32_t,uint32_t* n){
 *n=fail==3?UINT32_MAX:480;return fail==1?-1:0;}
int esp_ae_rate_cvt_process(void*,void*,uint32_t,void*,uint32_t* n){
 *n=fail==4?481:480;return fail==2?-1:0;}
struct Codec {int output_sample_rate(){return 24000;}};
struct AudioService {
 Codec storage;Codec* codec_=&storage;int decoder_sample_rate_=16000;
 void* output_resampler_=nullptr;
 bool ConvertOutputFrame(std::vector<int16_t>&);
};
''' + method + r'''
int main(){
 AudioService a;std::vector<int16_t> pcm(320,42);const auto original=pcm;
 assert(!a.ConvertOutputFrame(pcm)&&pcm==original);
 a.output_resampler_=&a;
 for(fail=1;fail<=4;++fail)assert(!a.ConvertOutputFrame(pcm)&&pcm==original);
 fail=0;assert(a.ConvertOutputFrame(pcm)&&pcm.size()==480);
 return 0;
}
''')

    def test_decoder_reconfiguration_failure_preserves_previous_working_state(self):
        source = (ROOT / "main/audio/audio_service.cc").read_text(encoding="utf-8")
        method = method_source(source, "bool AudioService::SetDecodeSampleRate(")
        self.compile_run(r'''
#include <cassert>
#include <mutex>
#include "audio_packet.h"
#define ESP_LOGE(...) ((void)0)
#define ESP_AUDIO_ERR_OK 0
#define ESP_AE_ERR_OK 0
#define ESP_AUDIO_MONO 1
struct esp_opus_dec_cfg_t {int rate,duration;};
struct esp_ae_rate_cvt_cfg_t {int src,dest,channel;};
using esp_ae_rate_cvt_handle_t=void*;
#define OPUS_DEC_CFG(r,d) esp_opus_dec_cfg_t{r,d}
#define RATE_CVT_CFG(s,d,c) esp_ae_rate_cvt_cfg_t{s,d,c}
bool decoder_fail=false,resampler_fail=false;
int decoder_closed=0,resampler_closed=0;
int esp_opus_dec_open(void*,size_t,void** p){*p=decoder_fail?nullptr:new int(1);return decoder_fail?-1:0;}
void esp_opus_dec_close(void* p){++decoder_closed;delete static_cast<int*>(p);}
int esp_ae_rate_cvt_open(void*,void** p){*p=resampler_fail?nullptr:new int(2);return resampler_fail?-1:0;}
void esp_ae_rate_cvt_close(void* p){++resampler_closed;delete static_cast<int*>(p);}
struct Codec {int output_sample_rate(){return 24000;}};
struct AudioService {
 Codec storage;Codec* codec_=&storage;
 std::mutex decoder_mutex_;
 void* opus_decoder_=nullptr;void* output_resampler_=nullptr;
 int decoder_sample_rate_=0,decoder_duration_ms_=0,decoder_frame_size_=0;
 bool SetDecodeSampleRate(int,int);
};
''' + method + r'''
int main(){
 AudioService a;assert(a.SetDecodeSampleRate(24000,60));auto old=a.opus_decoder_;
 decoder_fail=true;assert(!a.SetDecodeSampleRate(16000,20));
 assert(a.opus_decoder_==old&&a.decoder_sample_rate_==24000&&decoder_closed==0);
 decoder_fail=false;resampler_fail=true;assert(!a.SetDecodeSampleRate(16000,20));
 assert(a.opus_decoder_==old&&a.decoder_frame_size_==1440&&decoder_closed==1);
 resampler_fail=false;assert(a.SetDecodeSampleRate(16000,20));
 assert(a.output_resampler_&&a.decoder_sample_rate_==16000&&a.decoder_frame_size_==320);
 assert(!a.SetDecodeSampleRate(2147483647,2147483647));
 assert(a.decoder_sample_rate_==16000);
 assert(a.SetDecodeSampleRate(24000,60)&&!a.output_resampler_);
 esp_opus_dec_close(a.opus_decoder_);
 return 0;
}
''')

    def test_timer_does_not_cut_output_during_playback_or_block_other_timers(self):
        source = (ROOT / "main/audio/audio_service.cc").read_text(encoding="utf-8")
        method = method_source(source, "void AudioService::CheckAndUpdateAudioPowerState(")
        self.compile_run(r'''
#include <cassert>
#include <atomic>
#include <cstdint>
#include <mutex>
#include <thread>
#define AUDIO_POWER_TIMEOUT_MS 10000
#define AS_EVENT_AUDIO_INPUT_STOP_REQUEST 4
uint64_t clock_us=20000000;
uint64_t esp_timer_get_time(){return clock_us;}
void xEventGroupSetBits(int,int){}
struct Codec {
 bool input=false,output=true,duplex_=false;int shutdowns=0;
 bool input_enabled(){return input;} bool output_enabled(){return output;}
 bool duplex(){return duplex_;}
 void EnableOutput(bool enabled){output=enabled;if(!enabled)++shutdowns;}
};
struct AudioService {
 Codec storage;Codec* codec_=&storage;int event_group_=0;
 std::mutex output_power_mutex_,audio_queue_mutex_;
 std::atomic<uint32_t> last_input_time_ms_{0},last_output_time_ms_{0};
 bool drained=false;
 bool IsPlaybackDrainedLocked(){return drained;}
 void CheckAndUpdateAudioPowerState();
};
''' + method + r'''
int main(){
 AudioService a;
 a.CheckAndUpdateAudioPowerState();assert(a.storage.shutdowns==0);
 a.drained=true;
 {std::lock_guard<std::mutex> lock(a.output_power_mutex_);
  std::thread timer([&]{a.CheckAndUpdateAudioPowerState();});timer.join();}
 assert(a.storage.shutdowns==0);
 a.last_output_time_ms_=19999;a.CheckAndUpdateAudioPowerState();assert(a.storage.shutdowns==0);
 a.last_output_time_ms_=0;a.storage.duplex_=true;a.storage.input=true;
 a.CheckAndUpdateAudioPowerState();assert(a.storage.shutdowns==0);
 a.storage.input=false;a.CheckAndUpdateAudioPowerState();assert(a.storage.shutdowns==1);
 a.storage.output=true;clock_us=uint64_t(100)*1000;a.last_output_time_ms_=UINT32_MAX-50;
 a.CheckAndUpdateAudioPowerState();assert(a.storage.shutdowns==1); // Timer wrap is harmless.
 return 0;
}
''')

    def test_codec_failures_are_not_reported_as_valid_microphone_or_playback_data(self):
        source = (ROOT / "main/audio/codecs/es8311_audio_codec.cc").read_text(encoding="utf-8")
        read = method_source(source, "int Es8311AudioCodec::Read(")
        write = method_source(source, "int Es8311AudioCodec::Write(")
        self.compile_run(r'''
#include <cassert>
#include <cstdint>
#include <limits>
#define ESP_OK 0
#define ESP_LOGE(...) ((void)0)
int error=0,calls=0;
int esp_codec_dev_read(void*,void*,int){++calls;return error;}
int esp_codec_dev_write(void*,void*,int){++calls;return error;}
struct Es8311AudioCodec {
 bool input_enabled_=false,output_enabled_=false;void* dev_=nullptr;
 int Read(int16_t*,int);int Write(const int16_t*,int);
};
''' + read + write + r'''
int main(){
 Es8311AudioCodec a;int16_t pcm[320]{};
 assert(a.Read(pcm,320)==0&&a.Write(pcm,320)==0&&calls==0);
 a.input_enabled_=a.output_enabled_=true;a.dev_=&a;
 error=-1;assert(a.Read(pcm,320)==0&&a.Write(pcm,320)==0);
 error=0;assert(a.Read(pcm,320)==320&&a.Write(pcm,320)==320);
 const auto old=calls;assert(a.Read(nullptr,320)==0&&a.Write(pcm,INT32_MAX)==0&&calls==old);
 return 0;
}
''')
