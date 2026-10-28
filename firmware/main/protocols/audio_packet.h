#pragma once

#include <cstddef>
#include <cstdint>

namespace audio_packet {
// Covers the supported Opus packet durations without allowing arbitrary network allocations.
constexpr size_t kMaxPayloadBytes = 8192;

inline bool ValidPayloadSize(size_t size) { return size > 0 && size <= kMaxPayloadBytes; }

inline bool ValidFormat(int sample_rate, int duration_ms) {
    const bool rate = sample_rate == 8000 || sample_rate == 12000 || sample_rate == 16000 ||
                      sample_rate == 24000 || sample_rate == 48000;
    const bool duration = duration_ms == 5 || duration_ms == 10 || duration_ms == 20 ||
                          duration_ms == 40 || duration_ms == 60 || duration_ms == 80 ||
                          duration_ms == 100 || duration_ms == 120;
    return rate && duration;
}

struct Frame {
    const uint8_t* payload = nullptr;
    size_t size = 0;
    uint32_t timestamp = 0;
};

inline uint32_t Read32(const uint8_t* p) {
    return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3];
}

inline bool ParseWebSocket(int version, const char* data, size_t length, Frame& frame) {
    frame = {};
    if (data == nullptr)
        return false;
    const auto* bytes = reinterpret_cast<const uint8_t*>(data);
    size_t header = 0, size = length;
    uint32_t timestamp = 0;
    if (version == 2) {
        header = 16;
        if (length < header || bytes[0] != 0 || bytes[1] != 2 || bytes[2] != 0 || bytes[3] != 0)
            return false;
        timestamp = Read32(bytes + 8);
        size = Read32(bytes + 12);
    } else if (version == 3) {
        header = 4;
        if (length < header || bytes[0] != 0)
            return false;
        size = (size_t(bytes[2]) << 8) | bytes[3];
    } else if (version != 1) {
        return false;
    }
    if (!ValidPayloadSize(size) || size != length - header)
        return false;
    frame = {bytes + header, size, timestamp};
    return true;
}
}  // namespace audio_packet
