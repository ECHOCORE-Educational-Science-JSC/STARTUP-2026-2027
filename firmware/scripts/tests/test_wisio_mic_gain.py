"""Exercise the actual Wisio enclosure gain through the codec input override."""
import unittest
import test_music_atomic as atomic
from test_server_greeting import method_source
ROOT=atomic.ROOT
class WisioMicGainTests(unittest.TestCase):
    _compile_run=atomic.AtomicMusicTests._compile_run
    def test_quiet_voice_is_boosted_and_full_scale_never_overflows(self):
        source=(ROOT/'main/boards/freenove-esp32s3-display-2.8-lcd/freenove-esp32s3-display-2.8-lcd.cc').read_text(encoding='utf-8')
        method=method_source(source,'    bool InputData(')
        self._compile_run(r'''
#include <cassert>
#include <algorithm>
#include "audio/wisio_microphone_gain.h"
struct Es8311AudioCodec {bool ok=true;virtual bool InputData(std::vector<int16_t>&){return ok;}};
struct WisioAudioCodec:Es8311AudioCodec{METHOD};
int main(){
 WisioAudioCodec codec;std::vector<int16_t> silence(320,0);assert(codec.InputData(silence));
 assert(std::all_of(silence.begin(),silence.end(),[](int n){return n==0;}));
 std::vector<int16_t> quiet={1000,-1000,100,-100};codec.InputData(quiet);
 assert(quiet[0]==1414 && quiet[1]==-1414 && quiet[2]==141 && quiet[3]==-141);
 std::vector<int16_t> loud={32767,-32768,25000,-25000};codec.InputData(loud);
 for(auto n:loud)assert(n>=-30000 && n<=30000);
 assert(loud[0]>29000 && loud[1]<-29000);
 std::vector<int16_t> failed={1000,-1000};codec.ok=false;
 assert(!codec.InputData(failed) && failed[0]==1000 && failed[1]==-1000);
 std::vector<int16_t> empty;codec.ok=true;assert(codec.InputData(empty) && empty.empty());
}
'''.replace('METHOD',method))
        self.assertIn('static WisioAudioCodec audio_codec(',source)
    def test_recovery_keeps_mono_capture_and_speaker_pcm_unchanged(self):
        source=(ROOT/'main/boards/freenove-esp32s3-display-2.8-lcd/freenove-esp32s3-display-2.8-lcd.cc').read_text(encoding='utf-8')
        codec=source[source.index('class WisioAudioCodec :'):source.index('class WisioStatusLed :')]
        self._compile_run(r'''
#include <cassert>
#include "audio/wisio_microphone_gain.h"
struct Es8311AudioCodec {
 virtual ~Es8311AudioCodec()=default;
 virtual bool InputData(std::vector<int16_t>&){return true;}
 virtual int speech_gain_q15()const{return 32768;}
 int input_channels()const{return 1;}bool input_reference()const{return false;}
 virtual bool OutputData(std::vector<int16_t>&){return true;}
};
''' + codec + r'''
int main(){WisioAudioCodec codec;
 assert(codec.input_channels()==1&&!codec.input_reference());
 assert(codec.speech_gain_q15()==32768);
 std::vector<int16_t> p{32767,-32768,20000,-20000,1000,-1000};auto original=p;
 assert(codec.OutputData(p)&&p==original);
}
''')
if __name__=='__main__':unittest.main()
