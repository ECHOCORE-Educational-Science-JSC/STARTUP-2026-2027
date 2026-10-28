#include "custom_wake_word.h"
#include "audio_service.h"
#include "system_info.h"
#include "assets.h"

#include <esp_log.h>
#include <esp_mn_iface.h>
#include <esp_mn_models.h>
#include <esp_mn_speech_commands.h>
#include <cJSON.h>
#include <cmath>
#include <string_view>

#define TAG "CustomWakeWord"

// The Wisio profile ships every pronunciation in assets. Require those phonemes
// instead of guessing the coined name from English spelling at runtime.
#if (CONFIG_SR_MN_EN_MULTINET7_QUANT || CONFIG_SR_MN_EN_MULTINET5_SINGLE_RECOGNITION_QUANT8) && \
    defined(CONFIG_CUSTOM_WAKE_WORD)
static constexpr bool kRequireWisioPhonemes =
    std::string_view(CONFIG_CUSTOM_WAKE_WORD) == "HEY WISIO";
#else
static constexpr bool kRequireWisioPhonemes = false;
#endif

CustomWakeWord::CustomWakeWord()
    : wake_word_opus_() {
}

CustomWakeWord::~CustomWakeWord() {
    if (commands_allocated_) {
        esp_mn_commands_free();
    }
    if (multinet_model_data_ != nullptr && multinet_ != nullptr) {
        multinet_->destroy(multinet_model_data_);
        multinet_model_data_ = nullptr;
    }

    if (wake_word_encode_task_stack_ != nullptr) {
        heap_caps_free(wake_word_encode_task_stack_);
    }

    if (wake_word_encode_task_buffer_ != nullptr) {
        heap_caps_free(wake_word_encode_task_buffer_);
    }

    if (owns_models_ && models_ != nullptr) {
        esp_srmodel_deinit(models_);
    }
}

void CustomWakeWord::ParseWakenetModelConfig() {
    // Read index.json
    auto& assets = Assets::GetInstance();
    void* ptr = nullptr;
    size_t size = 0;
    if (!assets.GetAssetData("index.json", ptr, size)) {
        ESP_LOGE(TAG, "Failed to read index.json");
        return;
    }
    cJSON* root = cJSON_ParseWithLength(static_cast<char*>(ptr), size);
    if (root == nullptr) {
        ESP_LOGE(TAG, "Failed to parse index.json");
        return;
    }
    cJSON* multinet_model = cJSON_GetObjectItem(root, "multinet_model");
    if (cJSON_IsObject(multinet_model)) {
        cJSON* language = cJSON_GetObjectItem(multinet_model, "language");
        cJSON* duration = cJSON_GetObjectItem(multinet_model, "duration");
        cJSON* threshold = cJSON_GetObjectItem(multinet_model, "threshold");
        cJSON* commands = cJSON_GetObjectItem(multinet_model, "commands");
        if (cJSON_IsString(language)) {
            language_ = language->valuestring;
        }
        if (cJSON_IsNumber(duration)) {
            duration_ = duration->valueint;
        }
        if (cJSON_IsNumber(threshold)) {
            threshold_ = threshold->valuedouble;
        }
        if (cJSON_IsArray(commands)) {
            for (int i = 0; i < cJSON_GetArraySize(commands); i++) {
                cJSON* command = cJSON_GetArrayItem(commands, i);
                if (cJSON_IsObject(command)) {
                    cJSON* command_name = cJSON_GetObjectItem(command, "command");
                    cJSON* text = cJSON_GetObjectItem(command, "text");
                    cJSON* action = cJSON_GetObjectItem(command, "action");
                    cJSON* phonemes = cJSON_GetObjectItem(command, "phonemes");
                    if (cJSON_IsString(command_name) && cJSON_IsString(text) &&
                        cJSON_IsString(action)) {
                        commands_.push_back(
                            {command_name->valuestring, text->valuestring, action->valuestring,
                             cJSON_IsString(phonemes) ? phonemes->valuestring : ""});
                        ESP_LOGI(TAG, "Command: %s, Text: %s, Action: %s",
                                 command_name->valuestring, text->valuestring, action->valuestring);
                    }
                }
            }
        }
    }
    cJSON_Delete(root);
}

bool CustomWakeWord::Initialize(AudioCodec* codec, srmodel_list_t* models_list) {
    codec_ = codec;
    commands_.clear();

    if (models_list == nullptr) {
        language_ = "cn";
        models_ = esp_srmodel_init("model");
        owns_models_ = models_ != nullptr;
#ifdef CONFIG_CUSTOM_WAKE_WORD
        threshold_ = CONFIG_CUSTOM_WAKE_WORD_THRESHOLD / 100.0f;
        commands_.push_back({CONFIG_CUSTOM_WAKE_WORD, CONFIG_CUSTOM_WAKE_WORD_DISPLAY, "wake"});
#endif
    } else {
        models_ = models_list;
        ParseWakenetModelConfig();
    }

    if (models_ == nullptr || models_->num == -1) {
        ESP_LOGE(TAG, "Failed to initialize wakenet model");
        return false;
    }

    // 初始化 multinet (命令词识别)
    mn_name_ = esp_srmodel_filter(models_, ESP_MN_PREFIX, language_.c_str());
    if (mn_name_ == nullptr) {
        ESP_LOGW(TAG, "Language '%s' multinet not found, falling back to any multinet model",
                 language_.c_str());
        mn_name_ = esp_srmodel_filter(models_, ESP_MN_PREFIX, NULL);
    }
    if (mn_name_ == nullptr) {
        ESP_LOGE(TAG, "Failed to initialize multinet, mn_name is nullptr");
        ESP_LOGI(TAG,
                 "Please refer to https://pcn7cs20v8cr.feishu.cn/wiki/CpQjwQsCJiQSWSkYEvrcxcbVnwh "
                 "to add custom wake word");
        return false;
    }

    multinet_ = esp_mn_handle_from_name(mn_name_);
    if (multinet_ == nullptr || commands_.empty()) {
        ESP_LOGE(TAG, "No MultiNet interface or configured wake command");
        return false;
    }
    multinet_model_data_ = multinet_->create(mn_name_, duration_);
    if (multinet_model_data_ == nullptr) {
        ESP_LOGE(TAG, "Could not allocate MultiNet model");
        return false;
    }
    multinet_->set_det_threshold(multinet_model_data_, threshold_);
    input_buffer_.reserve(multinet_->get_samp_chunksize(multinet_model_data_));
    // The command registry must be bound to this model before clear/add/update.
    // Otherwise ESP-SR rejects every custom phrase, even with a valid model.
    if (esp_mn_commands_alloc(multinet_, multinet_model_data_) != ESP_OK) {
        ESP_LOGE(TAG, "Could not initialize the MultiNet command registry");
        return false;
    }
    commands_allocated_ = true;
    esp_mn_commands_clear();
    for (int i = 0; i < commands_.size(); i++) {
        const auto& command = commands_[i];
        esp_err_t status;
        if constexpr (kRequireWisioPhonemes) {
            if (command.phonemes.empty()) {
                ESP_LOGE(TAG, "Missing Hey Wisio phonemes; flash matching generated_assets.bin");
                return false;
            }
            status = esp_mn_commands_phoneme_add(i + 1, command.command.c_str(),
                                                 command.phonemes.c_str());
        } else {
            status = command.phonemes.empty()
                         ? esp_mn_commands_add(i + 1, command.command.c_str())
                         : esp_mn_commands_phoneme_add(i + 1, command.command.c_str(),
                                                       command.phonemes.c_str());
        }
        if (status != ESP_OK) {
            ESP_LOGE(TAG, "Wake command could not be registered: %s", commands_[i].command.c_str());
            return false;
        }
    }
    if (esp_mn_commands_update() != nullptr) {
        ESP_LOGE(TAG, "MultiNet rejected the wake command vocabulary");
        return false;
    }

    multinet_->print_active_speech_commands(multinet_model_data_);
#if CONFIG_SEND_WAKE_WORD_DATA
    if (!wake_word_audio_cache_.Initialize(16000 * 2)) {
        ESP_LOGW(TAG, "Wake-word audio upload disabled: PSRAM cache allocation failed");
    }
#endif
    return true;
}

void CustomWakeWord::OnWakeWordDetected(std::function<void(const std::string& wake_word)> callback) {
    wake_word_detected_callback_ = callback;
}

void CustomWakeWord::Start() {
    std::lock_guard<std::mutex> lock(input_buffer_mutex_);
    if (running_ || multinet_model_data_ == nullptr) {
        return;
    }
    // Every standby session starts with a fresh decoder, not a partial phrase
    // left behind by playback, listening, or a timed-out recognition window.
    multinet_->clean(multinet_model_data_);
    input_buffer_.clear();
    diagnostic_samples_ = 0;
    diagnostic_peak_ = 0;
    diagnostic_energy_ = 0;
    diagnostic_clipped_ = 0;
    diagnostic_detections_ = 0;
    diagnostic_timeouts_ = 0;
    running_ = true;
    ESP_LOGI(TAG, "Wake ready: %s, model=%s, threshold=%.2f", commands_.front().text.c_str(),
             mn_name_, threshold_);
}

void CustomWakeWord::Stop() {
    running_ = false;

    std::lock_guard<std::mutex> lock(input_buffer_mutex_);
    input_buffer_.clear();
}

void CustomWakeWord::Feed(const std::vector<int16_t>& data) {
    FeedSamples(data.data(), data.size(), false);
}

void CustomWakeWord::FeedMono(const int16_t* data, size_t samples) {
    FeedSamples(data, samples, true);
}

void CustomWakeWord::FeedSamples(const int16_t* data, size_t samples, bool mono) {
    if (multinet_model_data_ == nullptr || data == nullptr || samples == 0) {
        return;
    }

    std::unique_lock<std::mutex> lock(input_buffer_mutex_);
    // Check running state inside lock to avoid TOCTOU race with Stop()
    if (!running_) {
        return;
    }
    const int chunksize = multinet_->get_samp_chunksize(multinet_model_data_);
    if (chunksize <= 0)
        return;

    // One summary per ten seconds while waiting; no per-frame UART traffic.
    const size_t stride = mono ? 1 : codec_->input_channels();
    for (size_t i = 0; i < samples; i += stride) {
        const int value = data[i];
        const int magnitude = value < 0 ? -value : value;
        if (magnitude > diagnostic_peak_)
            diagnostic_peak_ = magnitude;
        ++diagnostic_samples_;
        diagnostic_energy_ += static_cast<uint64_t>(value * value);
        if (magnitude >= 32760)
            ++diagnostic_clipped_;
    }
    if (diagnostic_samples_ >= 16000 * 10) {
        ESP_LOGI(TAG,
                 "Wake listening: peak=%d rms=%.0f clipped=%.1f%% candidates=%u timeouts=%u (10s)",
                 diagnostic_peak_, std::sqrt(double(diagnostic_energy_) / diagnostic_samples_),
                 100.0 * diagnostic_clipped_ / diagnostic_samples_, diagnostic_detections_,
                 diagnostic_timeouts_);
        diagnostic_samples_ = 0;
        diagnostic_peak_ = 0;
        diagnostic_energy_ = 0;
        diagnostic_clipped_ = 0;
        diagnostic_detections_ = 0;
        diagnostic_timeouts_ = 0;
    }

    // If input channels is 2, we need to fetch the left channel data
    if (!mono && codec_->input_channels() > 1) {
        for (size_t i = 0; i < samples; i += codec_->input_channels()) {
            input_buffer_.push_back(data[i]);
        }
    } else {
        input_buffer_.insert(input_buffer_.end(), data, data + samples);
    }

    while (input_buffer_.size() >= chunksize) {
#if CONFIG_SEND_WAKE_WORD_DATA
        wake_word_audio_cache_.Store(input_buffer_.data(), chunksize);
#endif

        esp_mn_state_t mn_state = multinet_->detect(multinet_model_data_, input_buffer_.data());

        if (mn_state == ESP_MN_STATE_DETECTED) {
            ++diagnostic_detections_;
            esp_mn_results_t *mn_result = multinet_->get_results(multinet_model_data_);
            for (int i = 0; mn_result != nullptr && i < mn_result->num &&
                            i < ESP_MN_RESULT_MAX_NUM && running_;
                 i++) {
                const int command_id = mn_result->command_id[i];
                if (command_id <= 0 || static_cast<size_t>(command_id) > commands_.size() ||
                    !std::isfinite(mn_result->prob[i]) || mn_result->prob[i] < threshold_)
                    continue;
                ESP_LOGI(TAG, "Custom wake word detected: command_id=%d, string=%s, prob=%f",
                         mn_result->command_id[i], mn_result->string, mn_result->prob[i]);
                auto& command = commands_[command_id - 1];
                if (command.action == "wake") {
                    last_detected_wake_word_ = command.text;
                    running_ = false;
                    input_buffer_.clear();

                    multinet_->clean(multinet_model_data_);
                    const auto callback = wake_word_detected_callback_;
                    const auto detected = last_detected_wake_word_;
                    // A callback may stop/reconfigure wake and acquire AFE locks.
                    // Never call it while holding the detector's feed mutex.
                    lock.unlock();
                    if (callback)
                        callback(detected);
                    return;
                }
            }
            multinet_->clean(multinet_model_data_);
        } else if (mn_state == ESP_MN_STATE_TIMEOUT) {
            ++diagnostic_timeouts_;
            ESP_LOGD(TAG, "Command word detection timeout, cleaning state");
            multinet_->clean(multinet_model_data_);
        }
        
        if (!running_) {
            break;
        }
        input_buffer_.erase(input_buffer_.begin(), input_buffer_.begin() + chunksize);
    }
}

size_t CustomWakeWord::GetFeedSize() {
    if (multinet_model_data_ == nullptr) {
        return 0;
    }
    return multinet_->get_samp_chunksize(multinet_model_data_);
}

void CustomWakeWord::EncodeWakeWordData() {
    const size_t stack_size = 4096 * 7;
    wake_word_opus_.clear();
    if (wake_word_encode_task_stack_ == nullptr) {
        wake_word_encode_task_stack_ = (StackType_t*)heap_caps_malloc(stack_size, MALLOC_CAP_SPIRAM);
        assert(wake_word_encode_task_stack_ != nullptr);
    }
    if (wake_word_encode_task_buffer_ == nullptr) {
        wake_word_encode_task_buffer_ = (StaticTask_t*)heap_caps_malloc(sizeof(StaticTask_t), MALLOC_CAP_INTERNAL);
        assert(wake_word_encode_task_buffer_ != nullptr);
    }

    wake_word_encode_task_ = xTaskCreateStatic([](void* arg) {
        auto this_ = (CustomWakeWord*)arg;
        {
            auto start_time = esp_timer_get_time();
            // Create encoder
            esp_opus_enc_config_t opus_enc_cfg = AS_OPUS_ENC_CONFIG();
            void* encoder_handle = nullptr;
            auto ret = esp_opus_enc_open(&opus_enc_cfg, sizeof(esp_opus_enc_config_t), &encoder_handle);
            if (encoder_handle == nullptr) {
                ESP_LOGE(TAG, "Failed to create audio encoder, error code: %d", ret);
                this_->wake_word_audio_cache_.Clear();
                std::lock_guard<std::mutex> lock(this_->wake_word_mutex_);
                this_->wake_word_opus_.push_back(std::vector<uint8_t>());
                this_->wake_word_cv_.notify_all();
                vTaskDelete(nullptr);
                return;
            }
            // Get frame size
            int frame_size = 0;
            int outbuf_size = 0;
            esp_opus_enc_get_frame_size(encoder_handle, &frame_size, &outbuf_size);
            frame_size = frame_size / sizeof(int16_t);
            // Encode all PCM data
            int packets = 0;
            std::vector<int16_t> in_buffer(frame_size);
            esp_audio_enc_in_frame_t in = {};
            esp_audio_enc_out_frame_t out = {};
            const size_t cached_samples = this_->wake_word_audio_cache_.Size();
            for (size_t offset = 0;
                 offset + static_cast<size_t>(frame_size) <= cached_samples;
                 offset += frame_size) {
                if (this_->wake_word_audio_cache_.Read(
                        offset, in_buffer.data(), frame_size) != static_cast<size_t>(frame_size)) {
                    break;
                }
                std::vector<uint8_t> opus_buf(outbuf_size);
                in.buffer = reinterpret_cast<uint8_t*>(in_buffer.data());
                in.len = frame_size * sizeof(int16_t);
                out.buffer = opus_buf.data();
                out.len = outbuf_size;
                out.encoded_bytes = 0;
                ret = esp_opus_enc_process(encoder_handle, &in, &out);
                if (ret == ESP_AUDIO_ERR_OK) {
                    std::lock_guard<std::mutex> lock(this_->wake_word_mutex_);
                    this_->wake_word_opus_.emplace_back(opus_buf.data(), opus_buf.data() + out.encoded_bytes);
                    this_->wake_word_cv_.notify_all();
                    packets++;
                } else {
                    ESP_LOGE(TAG, "Failed to encode audio, error code: %d", ret);
                }
            }
            this_->wake_word_audio_cache_.Clear();
            // Close encoder
            esp_opus_enc_close(encoder_handle);
            auto end_time = esp_timer_get_time();
            ESP_LOGI(TAG, "Encode wake word opus %d packets in %ld ms", packets, (long)((end_time - start_time) / 1000));

            std::lock_guard<std::mutex> lock(this_->wake_word_mutex_);
            this_->wake_word_opus_.push_back(std::vector<uint8_t>());
            this_->wake_word_cv_.notify_all();
        }
        vTaskDelete(NULL);
    }, "encode_wake_word", stack_size, this, 2, wake_word_encode_task_stack_, wake_word_encode_task_buffer_);
}

bool CustomWakeWord::GetWakeWordOpus(std::vector<uint8_t>& opus) {
    std::unique_lock<std::mutex> lock(wake_word_mutex_);
    wake_word_cv_.wait(lock, [this]() {
        return !wake_word_opus_.empty();
    });
    opus.swap(wake_word_opus_.front());
    wake_word_opus_.pop_front();
    return !opus.empty();
}
