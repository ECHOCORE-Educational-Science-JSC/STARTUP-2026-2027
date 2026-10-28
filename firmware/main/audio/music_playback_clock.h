#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>

// AudioService serializes this state with its queue mutex. Count mono output
// samples only after the codec accepts a full frame, never packets sent by a server.
class MusicPlaybackClock {
public:
    uint32_t Start(uint32_t sample_rate) {
        if (++sequence_ == 0)
            ++sequence_;
        epoch_ = sample_rate ? sequence_ : 0;
        sample_rate_ = sample_rate;
        samples_ = 0;
        return epoch_;
    }

    void Stop() {
        epoch_ = 0;
        samples_ = 0;
    }
    uint32_t epoch() const { return epoch_; }

    void Written(uint32_t epoch, size_t samples) {
        if (epoch == 0 || epoch != epoch_ || sample_rate_ == 0)
            return;
        const uint64_t cap = uint64_t(sample_rate_) * std::numeric_limits<uint32_t>::max() / 1000;
        samples_ += std::min<uint64_t>(samples, cap - samples_);
    }

    uint32_t PositionMs() const {
        return epoch_ && sample_rate_ ? static_cast<uint32_t>(samples_ * 1000 / sample_rate_) : 0;
    }

private:
    uint32_t sequence_ = 0;
    uint32_t epoch_ = 0;
    uint32_t sample_rate_ = 0;
    uint64_t samples_ = 0;
};
