#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <mutex>
#include <vector>

// Digital speaker reference for the fixed 24 kHz Freenove codec. This is not an
// ADC reference: timestamps and correlation compensate the software/DMA delay.
// All storage is bounded; no wait for speaker I/O is held under this mutex.
class WisioPlaybackReference {
public:
    static constexpr int kRate = 24000;
    static constexpr int kSearch = kRate * 80 / 1000;
    static constexpr int kCapacity = 12288;
    void Clear() {
        std::lock_guard<std::mutex> lock(mutex_);
        begin_ = end_ = next_ = 0;
    }
    void Publish(const std::vector<int16_t>& pcm, int64_t now_us) {
        std::lock_guard<std::mutex> lock(mutex_);
        const int64_t now = now_us * kRate / 1000000;
        const int64_t start = std::max(now, next_);
        if (start - end_ >= kCapacity)
            begin_ = end_ = start;
        while (end_ < start)
            ring_[end_++ % kCapacity] = 0;
        for (const auto sample : pcm)
            ring_[end_++ % kCapacity] = sample;
        next_ = end_;
        begin_ = std::max(begin_, end_ - kCapacity);
    }
    void Interleave(const std::vector<int16_t>& mic, int64_t captured_at_us,
                    std::vector<int16_t>& stereo) {
        const size_t count = mic.size();
        stereo.resize(count * 2);
        // Readback can lag the live ADC by the I2S DMA depth. Search either side
        // of that estimate, retaining the last alignment during float talk.
        const int64_t first = captured_at_us * kRate / 1000000 - int64_t(count) - kRate * 60 / 1000;
        snapshot_.resize(count + 2 * kSearch);
        bool have_reference = false;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            for (size_t i = 0; i < snapshot_.size(); ++i) {
                const int64_t position = first - kSearch + int64_t(i);
                snapshot_[i] =
                    position >= begin_ && position < end_ ? ring_[position % kCapacity] : 0;
                have_reference = have_reference || snapshot_[i] != 0;
            }
        }
        float mic_energy = 0;
        for (size_t i = 0; i < count; i += 6)
            mic_energy += float(mic[i]) * mic[i];
        float best_score = 0.42f;  // squared normalized correlation > 0.65
        int best_offset = offset_;
        if (have_reference && mic_energy > count * 10000.0f) {
            for (int offset = 0; offset <= 2 * kSearch; offset += 24) {
                float dot = 0, energy = 0;
                for (size_t i = 0; i < count; i += 6) {
                    const float reference = snapshot_[offset + i];
                    dot += mic[i] * reference;
                    energy += reference * reference;
                }
                if (energy < count * 10000.0f)
                    continue;
                const float score = dot * dot / (mic_energy * energy);
                if (score > best_score) {
                    best_score = score;
                    best_offset = offset;
                }
            }
        }
        offset_ = best_offset;
        for (size_t i = 0; i < count; ++i) {
            stereo[2 * i] = mic[i];
            stereo[2 * i + 1] = snapshot_[offset_ + i];
        }
    }

private:
    std::array<int16_t, kCapacity> ring_{};
    std::mutex mutex_;
    int64_t begin_ = 0, end_ = 0, next_ = 0;
    int offset_ = kSearch;
    std::vector<int16_t> snapshot_;  // owned exclusively by the input task
};
