"""Soft emerging speech is voice; ordinary thinking pauses are not mistakes."""
import unittest
import bridge


class ChildSpeechTest(unittest.TestCase):
    def test_soft_voice_in_quiet_room_starts_after_two_real_frames(self):
        state = bridge.new_speech_state()
        for _ in range(10):
            self.assertFalse(bridge.voice_onset_detected(state, 30))
        self.assertFalse(bridge.voice_onset_detected(state, 220))
        self.assertTrue(bridge.voice_onset_detected(state, 240))

    def test_soft_voice_is_tracked_and_thinking_pause_allows_continuation(self):
        state = bridge.new_speech_state()
        state['ambient_level'] = 30
        for i in range(8):
            self.assertFalse(bridge.update_speech_state(state, 220, i*.06))
        self.assertTrue(state['heard_voice'])
        for i in range(8, 38):
            self.assertFalse(bridge.update_speech_state(state, 30, i*.06))
        self.assertFalse(bridge.update_speech_state(state, 220, 38*.06))
        for i in range(39, 125):
            ended = bridge.update_speech_state(state, 30, i*.06)
            if ended:
                break
        # Enough actual silence eventually finishes the turn; no endless mic wait.
        self.assertTrue(ended)

    def test_single_click_does_not_become_a_childs_utterance(self):
        state = bridge.new_speech_state()
        for _ in range(10):
            self.assertFalse(bridge.voice_onset_detected(state, 50))
        self.assertFalse(bridge.voice_onset_detected(state, 900))
        self.assertFalse(bridge.voice_onset_detected(state, 50))
        self.assertFalse(bridge.voice_onset_detected(state, 900))

    def test_fan_noise_is_not_soft_english_speech(self):
        state = bridge.new_speech_state()
        for _ in range(40):
            self.assertFalse(bridge.voice_onset_detected(state, 1200))
        self.assertFalse(bridge.voice_onset_detected(state, 1400))


if __name__ == '__main__':
    unittest.main()
