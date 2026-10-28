"""Offline FFmpeg signal checks of the production small-speaker music filter."""
import array
import math
import subprocess
import unittest
import music

class MusicHeadroomTests(unittest.TestCase):
    def render(self, amplitude, frequency, filtered=True):
        tone=f"aevalsrc={amplitude}*sin(2*PI*{frequency}*t)|{amplitude}*sin(2*PI*{frequency}*t):s=48000:d=0.3"
        command=[music._ffmpeg_executable(),'-hide_banner','-loglevel','error',
                 '-f','lavfi','-i',tone]
        if filtered:command += ['-af',music.MUSIC_AUDIO_FILTER]
        command += ['-ac','1','-ar','24000','-f','s16le','pipe:1']
        output=subprocess.run(command,capture_output=True,timeout=15)
        self.assertEqual(output.returncode,0,output.stderr.decode(errors='replace'))
        pcm=array.array('h');pcm.frombytes(output.stdout)
        self.assertGreater(len(pcm),6000)
        return pcm

    def test_hot_stereo_music_keeps_headroom_and_duration(self):
        pcm=self.render(1.8,1000)
        self.assertLessEqual(max(abs(n) for n in pcm),24600)
        self.assertAlmostEqual(len(pcm)/24000,0.3,delta=1/24000)
        raw=self.render(1.8,1000,False)
        self.assertGreater(max(abs(n) for n in raw),32000)

    def test_quiet_music_is_not_boosted_back_to_full_scale(self):
        pcm=self.render(0.1,1000)
        raw=self.render(0.1,1000,False)
        # Compare against the same stereo downmix, whose power-preserving
        # coefficients can exceed the amplitude of either input channel.
        rms=lambda x:math.sqrt(sum(n*n for n in x)/len(x))
        self.assertLessEqual(rms(pcm[2400:]),rms(raw[2400:])*1.03)
        self.assertGreater(rms(pcm[2400:]),rms(raw[2400:])*0.95)
        self.assertLess(max(abs(n) for n in pcm),6000)

    def test_deep_bass_is_attenuated_without_erasing_midrange(self):
        bass=self.render(0.2,40)[2400:]
        mid=self.render(0.2,1000)[2400:]
        rms=lambda x:math.sqrt(sum(n*n for n in x)/len(x))
        self.assertLess(rms(bass),rms(mid)*0.25)

if __name__=='__main__':unittest.main()
