#pragma once

#include <cstdint>

// Only feed a real hardware charging signal here, never a battery-voltage trend.
class ChargingStatusFilter {
public:
    constexpr bool UpdateLevel(bool high, bool active_low, int64_t now_us) {
        return Update(high != active_low, now_us);
    }

    constexpr bool Update(bool connected, int64_t now_us) {
        if (!initialized_ || candidate_ != connected) {
            initialized_ = true;
            candidate_ = connected;
            candidate_since_us_ = now_us;
        }
        if (now_us - candidate_since_us_ >= 200000) {
            stable_ = candidate_;
        }
        return stable_;
    }

private:
    bool initialized_ = false;
    bool candidate_ = false;
    bool stable_ = false;
    int64_t candidate_since_us_ = 0;
};
