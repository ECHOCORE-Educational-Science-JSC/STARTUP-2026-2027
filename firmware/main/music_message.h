#ifndef MUSIC_MESSAGE_H_
#define MUSIC_MESSAGE_H_

#include <cstddef>
#include <cstdint>
#include <cstring>

enum class MusicMessageState { kInvalid, kStart, kCover, kProgress, kStop };

inline MusicMessageState ParseMusicMessageState(const char* state) {
    if (state == nullptr) {
        return MusicMessageState::kInvalid;
    }
    if (strcmp(state, "start") == 0) {
        return MusicMessageState::kStart;
    }
    if (strcmp(state, "cover") == 0) {
        return MusicMessageState::kCover;
    }
    if (strcmp(state, "progress") == 0) {
        return MusicMessageState::kProgress;
    }
    if (strcmp(state, "stop") == 0) {
        return MusicMessageState::kStop;
    }
    return MusicMessageState::kInvalid;
}

inline uint32_t ClampMusicPosition(uint32_t position_ms, uint32_t duration_ms) {
    return duration_ms > 0 && position_ms > duration_ms ? duration_ms : position_ms;
}

inline bool IsMusicCoverPng(const uint8_t* bytes, size_t size) {
    constexpr uint8_t kSignature[] = {0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'};
    if (bytes == nullptr || size < 24 || memcmp(bytes, kSignature, sizeof(kSignature)) != 0 ||
        memcmp(bytes + 12, "IHDR", 4) != 0) {
        return false;
    }
    auto read_u32 = [bytes](size_t offset) {
        return (static_cast<uint32_t>(bytes[offset]) << 24) |
               (static_cast<uint32_t>(bytes[offset + 1]) << 16) |
               (static_cast<uint32_t>(bytes[offset + 2]) << 8) | bytes[offset + 3];
    };
    const auto width = read_u32(16);
    const auto height = read_u32(20);
    // Bound decoder work and image memory even when a valid-looking payload is hostile.
    return width > 0 && height > 0 && width <= 1024 && height <= 1024 &&
           static_cast<uint64_t>(width) * height <= 320 * 240;
}

#endif  // MUSIC_MESSAGE_H_
