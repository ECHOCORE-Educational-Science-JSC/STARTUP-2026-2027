#include "audio_codec.h"
#include "board.h"
#include "settings.h"

#include <driver/i2s_common.h>
#include <esp_log.h>
#include <algorithm>
#include <cstring>

#define TAG "AudioCodec"

AudioCodec::AudioCodec() {
}

AudioCodec::~AudioCodec() {
}

bool AudioCodec::OutputData(std::vector<int16_t>& data) {
    const int written = Write(data.data(), data.size());
    return written > 0 && static_cast<size_t>(written) == data.size();
}

bool AudioCodec::InputData(std::vector<int16_t>& data) {
    int samples = Read(data.data(), data.size());
    // Callers require a complete frame; never feed stale tail samples to VAD/wake.
    return samples > 0 && static_cast<size_t>(samples) == data.size();
}

void AudioCodec::Start() {
    Settings settings("audio", false);
    output_volume_ = settings.GetInt("output_volume", output_volume_);
    output_volume_ = std::clamp(output_volume_, 0, 100);

    ESP_LOGI(TAG, "Audio codec started");
}

void AudioCodec::SetOutputVolume(int volume) {
    output_volume_ = std::clamp(volume, 0, 100);
    ESP_LOGI(TAG, "Set output volume to %d", output_volume_);
    
    Settings settings("audio", true);
    settings.SetInt("output_volume", output_volume_);
}

void AudioCodec::SetInputGain(float gain) {
    input_gain_ = gain;
    ESP_LOGI(TAG, "Set input gain to %.1f", input_gain_);
}

void AudioCodec::EnableInput(bool enable) {
    if (enable == input_enabled_) {
        return;
    }
    input_enabled_ = enable;
    ESP_LOGI(TAG, "Set input enable to %s", enable ? "true" : "false");
}

void AudioCodec::EnableOutput(bool enable) {
    if (enable == output_enabled_) {
        return;
    }
    output_enabled_ = enable;
    ESP_LOGI(TAG, "Set output enable to %s", enable ? "true" : "false");
}
