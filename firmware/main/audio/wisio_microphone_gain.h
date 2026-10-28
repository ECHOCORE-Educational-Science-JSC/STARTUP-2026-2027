#pragma once
#include <algorithm>
#include <cstdint>
#include <vector>

// +3 dB for the Freenove microphone behind its enclosure. Compute headroom
// before multiplication, including INT16_MIN, so loud input never wraps.
inline void ApplyWisioMicrophoneGain(std::vector<int16_t>& pcm) {
    int32_t peak = 0;
    for (const auto sample : pcm) {
        const int32_t value = sample;
        peak = std::max(peak, value < 0 ? -value : value);
    }
    if (peak == 0)
        return;
    const int32_t gain_q15 = std::min<int32_t>(46341, 30000 * 32768 / peak);
    for (auto& sample : pcm) {
        const int32_t value = static_cast<int32_t>(sample) * gain_q15;
        sample = static_cast<int16_t>((value + (value >= 0 ? 16384 : -16384)) / 32768);
    }
}
