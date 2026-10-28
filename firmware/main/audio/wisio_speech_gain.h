#pragma once
#include <cstdint>
#include <vector>

// Boost quiet speech without increasing the analog amplifier ceiling used by music.
// A continuous soft knee leaves headroom for the DAC; unity is an exact bypass.
inline void ApplyWisioSpeechGain(std::vector<int16_t>& pcm, int gain_q15) {
    if (gain_q15 <= 32768)
        return;
    for (auto& sample : pcm) {
        const int64_t amplified = int64_t(sample) * gain_q15 / 32768;
        const int64_t magnitude = amplified < 0 ? -amplified : amplified;
        const int64_t limited =
            magnitude <= 24000 ? magnitude
                               : 24000 + 6000 * (magnitude - 24000) / (magnitude - 24000 + 6000);
        sample = static_cast<int16_t>(amplified < 0 ? -limited : limited);
    }
}
