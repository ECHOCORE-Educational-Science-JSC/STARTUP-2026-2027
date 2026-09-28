#ifndef MUSIC_MESSAGE_H_
#define MUSIC_MESSAGE_H_

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

#endif  // MUSIC_MESSAGE_H_
