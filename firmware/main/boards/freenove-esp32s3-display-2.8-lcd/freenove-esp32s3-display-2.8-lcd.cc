#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_ops.h>
#include <esp_lcd_panel_vendor.h>

#include <wifi_station.h>
#include "adc_battery_monitor.h"
#include "application.h"
#include "assets/lang_config.h"
#include "button.h"
#include "codecs/es8311_audio_codec.h"
#include "config.h"
#include "display/lcd_display.h"
#include "lvgl_theme.h"
#include "mcp_server.h"
#include "settings.h"
#include "wifi_board.h"

#include <driver/i2c_master.h>
#include <driver/spi_common.h>
#include <esp_log.h>
#include <esp_timer.h>
#include <esp_wifi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>

#include "esp_lcd_ili9341.h"
#include "led/single_led.h"
#include "system_reset.h"

#define TAG "FreenoveESP32S3Display"

LV_FONT_DECLARE(BUILTIN_TEXT_FONT);
LV_FONT_DECLARE(echocore_pixel_font);
extern const uint8_t wisio_loading_bg_start[] asm("_binary_wisio_loading_bg_png_start");
extern const uint8_t wisio_loading_bg_end[] asm("_binary_wisio_loading_bg_png_end");

#define DECLARE_MOCHI(name)                                                               \
    extern const uint8_t mochi_##name##_start[] asm("_binary_mochi_" #name "_gif_start"); \
    extern const uint8_t mochi_##name##_end[] asm("_binary_mochi_" #name "_gif_end")
DECLARE_MOCHI(neutral);
DECLARE_MOCHI(happy);
DECLARE_MOCHI(laughing);
DECLARE_MOCHI(sad);
DECLARE_MOCHI(crying);
DECLARE_MOCHI(sleepy);
DECLARE_MOCHI(surprised);
DECLARE_MOCHI(thinking);
DECLARE_MOCHI(winking);
DECLARE_MOCHI(loving);
DECLARE_MOCHI(angry);
DECLARE_MOCHI(confident);
#undef DECLARE_MOCHI

class EchoCoreLcdDisplay : public SpiLcdDisplay {
public:
    using SpiLcdDisplay::SpiLcdDisplay;

    void SetupUI() override {
        mochi_faces_ = std::make_shared<EmojiCollection>();
        auto add_face = [this](const char* emotion, const uint8_t* first, const uint8_t* last) {
            mochi_faces_->AddEmoji(emotion,
                                   new LvglRawImage(const_cast<uint8_t*>(first), last - first));
        };
#define ADD_MOCHI(emotion, name) add_face(emotion, mochi_##name##_start, mochi_##name##_end)
        ADD_MOCHI("neutral", neutral);
        ADD_MOCHI("robot_2", neutral);
        ADD_MOCHI("relaxed", neutral);
        ADD_MOCHI("happy", happy);
        ADD_MOCHI("funny", happy);
        ADD_MOCHI("embarrassed", happy);
        ADD_MOCHI("laughing", laughing);
        ADD_MOCHI("silly", laughing);
        ADD_MOCHI("sad", sad);
        ADD_MOCHI("crying", crying);
        ADD_MOCHI("sleepy", sleepy);
        ADD_MOCHI("surprised", surprised);
        ADD_MOCHI("shocked", surprised);
        ADD_MOCHI("thinking", thinking);
        ADD_MOCHI("confused", thinking);
        ADD_MOCHI("winking", winking);
        ADD_MOCHI("loving", loving);
        ADD_MOCHI("kissy", loving);
        ADD_MOCHI("angry", angry);
        ADD_MOCHI("confident", confident);
        ADD_MOCHI("cool", confident);
        ADD_MOCHI("delicious", happy);
#undef ADD_MOCHI
        RestoreMochiFaces();
        SpiLcdDisplay::SetupUI();
        SetHideSubtitle(true);
        SetEmotion("neutral");
        DisplayLockGuard lock(this);
        // Replace the scrolling status words with one compact, unambiguous dot.
        lv_label_set_text(status_label_, "");
        lv_obj_add_flag(status_label_, LV_OBJ_FLAG_HIDDEN);
        status_indicator_ = MakeBlock(lv_screen_active(), 16, 16, width_ - 24, 8,
                                      kWaitingColor, LV_RADIUS_CIRCLE);
        lv_obj_add_flag(status_indicator_, LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_size(emoji_box_, width_, height_);
        lv_obj_center(emoji_box_);
        // Nothing below the boot layers should repaint while STARTING UP is visible.
        // In particular, a running GIF can invalidate the whole display and briefly
        // show through on a single-buffered SPI panel.
        lv_obj_add_flag(emoji_box_, LV_OBJ_FLAG_HIDDEN);
        splash_ = lv_obj_create(lv_screen_active());
        lv_obj_set_size(splash_, width_, height_);
        lv_obj_center(splash_);
        lv_obj_set_style_bg_color(splash_, lv_color_hex(0x000000), 0);
        lv_obj_set_style_bg_opa(splash_, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(splash_, 0, 0);
        lv_obj_set_style_radius(splash_, 0, 0);
        lv_obj_set_style_pad_all(splash_, 0, 0);
        lv_obj_set_scrollbar_mode(splash_, LV_SCROLLBAR_MODE_OFF);

        loading_descriptor_.header.magic = LV_IMAGE_HEADER_MAGIC;
        loading_descriptor_.header.cf = LV_COLOR_FORMAT_RAW_ALPHA;
        loading_descriptor_.data = wisio_loading_bg_start;
        loading_descriptor_.data_size = wisio_loading_bg_end - wisio_loading_bg_start;
        auto* artwork = lv_image_create(splash_);
        lv_image_set_src(artwork, &loading_descriptor_);
        lv_obj_set_pos(artwork, 0, 0);
        waves_[0][0] = MakeWave(89, 102, true);
        waves_[0][1] = MakeWave(218, 102, false);
        waves_[1][0] = MakeWave(78, 98, true);
        waves_[1][1] = MakeWave(229, 98, false);
        static constexpr int sparkle_xy[10][2] = {
            {41, 39},  {64, 82},  {103, 29},  {126, 91}, {206, 37},
            {260, 82}, {282, 46}, {233, 132}, {84, 141}, {295, 151},
        };
        for (int i = 0; i < 10; ++i) {
            sparkles_[i] =
                MakeBlock(splash_, i % 3 == 0 ? 3 : 2, i % 3 == 0 ? 3 : 2, sparkle_xy[i][0],
                          sparkle_xy[i][1], i % 2 == 0 ? 0xB4FAFF : 0x50D9FF, 0);
        }

        startup_phase_text_ = lv_label_create(splash_);
        lv_label_set_text(startup_phase_text_, "STARTING UP...");
        lv_obj_set_style_text_color(startup_phase_text_, lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_text_font(startup_phase_text_, &lv_font_montserrat_14, 0);
        lv_obj_set_pos(startup_phase_text_, 6, 179);

        progress_text_ = lv_label_create(splash_);
        lv_obj_set_style_text_color(progress_text_, lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_text_font(progress_text_, &lv_font_montserrat_14, 0);
        lv_obj_align(progress_text_, LV_ALIGN_TOP_RIGHT, -14, 179);
        lv_label_set_text(progress_text_, "0%");

        status_text_ = lv_label_create(splash_);
        lv_obj_set_style_text_color(status_text_, lv_color_hex(0x80F3ED), 0);
        lv_obj_set_style_text_font(status_text_, &lv_font_montserrat_14, 0);
        lv_obj_align(status_text_, LV_ALIGN_TOP_MID, 0, 179);
        lv_label_set_text(status_text_, "");

        auto* progress_track = MakeBlock(splash_, 300, 22, 10, 199, 0x063159, 11);
        lv_obj_set_style_border_width(progress_track, 1, 0);
        lv_obj_set_style_border_color(progress_track, lv_color_hex(0x7DEAFB), 0);
        progress_fill_ = MakeBlock(splash_, 1, 14, 14, 203, 0x32E3F2, 7);
        lv_obj_add_flag(progress_fill_, LV_OBJ_FLAG_HIDDEN);

        animation_ = lv_timer_create(
            [](lv_timer_t* timer) {
                static_cast<EchoCoreLcdDisplay*>(lv_timer_get_user_data(timer))->AnimateWaiting();
            },
            180, this);
        // The backlight stays dark until the complete first splash frame has
        // been rendered. This prevents the panel's cleared/partial buffer from
        // flashing before LVGL has finished drawing the startup UI.
        lv_obj_move_foreground(splash_);
        lv_obj_invalidate(splash_);
        lv_refr_now(nullptr);
        splash_started_us_ = esp_timer_get_time();
        if (auto* backlight = Board::GetInstance().GetBacklight())
            backlight->SetBrightness(100);
    }

    void SetEmotion(const char* emotion) override {
        if (!startup_complete_.load()) {
            std::lock_guard<std::mutex> guard(pending_emotion_mutex_);
            pending_emotion_ = emotion != nullptr ? emotion : "neutral";
            return;
        }
        const char* requested = emotion != nullptr ? emotion : "neutral";
        const int64_t now = esp_timer_get_time();
        if (std::strcmp(requested, "neutral") == 0 && now < emotion_hold_until_us_.load()) {
            neutral_pending_.store(true);
            return;
        }
        if (std::strcmp(requested, "neutral") != 0) {
            int64_t hold_ms = 4000;
            if (std::strcmp(requested, "sad") == 0 || std::strcmp(requested, "crying") == 0)
                hold_ms = 8000;
            else if (std::strcmp(requested, "happy") == 0 ||
                     std::strcmp(requested, "laughing") == 0 ||
                     std::strcmp(requested, "loving") == 0)
                hold_ms = 6000;
            emotion_hold_until_us_.store(now + hold_ms * 1000);
            neutral_pending_.store(false);
        } else {
            neutral_pending_.store(false);
        }
        // Assets::Apply() runs after SetupUI() and normally replaces the theme's
        // emoji collection with Xiaozhi's stock faces. Restore the board-owned
        // Mochi collection on every emotion change so the stock assets cannot
        // overwrite it during startup or a later theme refresh.
        RestoreMochiFaces();
        SpiLcdDisplay::SetEmotion(emotion);
    }

    bool IsStartupComplete() const override { return startup_complete_.load(); }

    void SetStatus(const char* status) override {
        DisplayLockGuard lock(this);
        if (status_indicator_ != nullptr) {
            uint32_t color = kWaitingColor;
            if (std::strcmp(status, Lang::Strings::SPEAKING) == 0) {
                color = kSpeakingColor;
            } else if (std::strcmp(status, Lang::Strings::LISTENING) == 0) {
                color = kListeningColor;
            }
            lv_obj_set_style_bg_color(status_indicator_, lv_color_hex(color), 0);
        }
        if (splash_ != nullptr) {
            if (std::strcmp(status, Lang::Strings::REGISTERING_NETWORK) == 0) {
                target_progress_ = 22;
                lv_label_set_text(status_text_, "");
            } else if (std::strcmp(status, Lang::Strings::CHECKING_NEW_VERSION) == 0) {
                target_progress_ = 42;
                lv_label_set_text(status_text_, "");
                loading_phase_requested_ = true;
            } else if (std::strcmp(status, Lang::Strings::LOADING_PROTOCOL) == 0 ||
                       std::strcmp(status, Lang::Strings::CONNECTING) == 0) {
                target_progress_ = 85;
                lv_label_set_text(status_text_, "");
                loading_phase_requested_ = true;
            } else if (std::strcmp(status, Lang::Strings::STANDBY) == 0) {
                target_progress_ = 100;
                lv_label_set_text(status_text_, "");
                ready_ = true;
            }
            if (!ready_)
                return;
        }
        // Status is represented by the colored dot; keep the stock text hidden.
        if (status_label_ != nullptr)
            lv_obj_add_flag(status_label_, LV_OBJ_FLAG_HIDDEN);
    }

    void ShowNotification(const char* notification, int duration_ms = 3000) override {
        if (splash_ != nullptr) {
            if (std::strstr(notification, "server") != nullptr) {
                DisplayLockGuard lock(this);
                lv_label_set_text(status_text_, "SERVER OFFLINE");
                target_progress_ = progress_;
            }
            return;
        }
        // The activation version is informational and need not cover the ready screen.
        if (std::strncmp(notification, Lang::Strings::VERSION,
                         std::strlen(Lang::Strings::VERSION)) == 0)
            return;
        SpiLcdDisplay::ShowNotification(notification, duration_ms);
    }

    void SetChatMessage(const char* role, const char* content) override {
        if (splash_ != nullptr && std::strcmp(role, "system") == 0)
            return;
        SpiLcdDisplay::SetChatMessage(role, content);
    }

private:
    std::shared_ptr<EmojiCollection> mochi_faces_;
    lv_image_dsc_t loading_descriptor_ = {};
    lv_obj_t* splash_ = nullptr;
    lv_obj_t* status_indicator_ = nullptr;
    lv_obj_t* sparkles_[10] = {};
    lv_obj_t* waves_[2][2] = {};
    lv_obj_t* status_text_ = nullptr;
    lv_obj_t* startup_phase_text_ = nullptr;
    lv_obj_t* progress_text_ = nullptr;
    lv_obj_t* progress_fill_ = nullptr;
    lv_obj_t* transition_mask_ = nullptr;
    lv_timer_t* animation_ = nullptr;
    int target_progress_ = 22;
    int progress_ = 0;
    bool ready_ = false;
    std::atomic<bool> startup_complete_{false};
    std::atomic<int64_t> emotion_hold_until_us_{0};
    std::atomic<bool> neutral_pending_{false};
    std::mutex pending_emotion_mutex_;
    std::string pending_emotion_ = "neutral";
    static constexpr uint32_t kSpeakingColor = 0xFFD43B;
    static constexpr uint32_t kListeningColor = 0x2DFF79;
    static constexpr uint32_t kWaitingColor = 0xFF3B4D;
    int completion_ticks_ = 0;
    unsigned tick_ = 0;
    bool transition_started_ = false;
    bool loading_phase_started_ = false;
    bool loading_phase_requested_ = false;
    int64_t splash_started_us_ = 0;

    static void SetObjectOpacity(void* object, int32_t opacity) {
        lv_obj_set_style_opa(static_cast<lv_obj_t*>(object), opacity, 0);
    }

    void BeginLoadingPhase() {
        if (loading_phase_started_ || startup_phase_text_ == nullptr)
            return;
        loading_phase_started_ = true;
        lv_label_set_text(startup_phase_text_, "LOADING...");
    }

    static void FinishFaceReveal(lv_anim_t* animation) {
        auto* self = static_cast<EchoCoreLcdDisplay*>(lv_anim_get_user_data(animation));
        if (self == nullptr || self->transition_mask_ == nullptr)
            return;
        lv_obj_delete(self->transition_mask_);
        self->transition_mask_ = nullptr;
    }

    static void SwapSplashToFace(lv_anim_t* animation) {
        auto* self = static_cast<EchoCoreLcdDisplay*>(lv_anim_get_user_data(animation));
        if (self == nullptr || self->splash_ == nullptr || self->transition_mask_ == nullptr)
            return;

        // Everything underneath is replaced while the panel is fully covered.
        // The user therefore never sees a cleared buffer or a half-decoded GIF.
        lv_obj_delete(self->splash_);
        self->splash_ = nullptr;
        lv_obj_remove_flag(self->emoji_box_, LV_OBJ_FLAG_HIDDEN);
        lv_obj_remove_flag(self->status_indicator_, LV_OBJ_FLAG_HIDDEN);
        lv_obj_move_foreground(self->transition_mask_);
        lv_refr_now(nullptr);

        std::string pending;
        {
            std::lock_guard<std::mutex> guard(self->pending_emotion_mutex_);
            pending = self->pending_emotion_;
        }
        self->startup_complete_.store(true);
        Application::GetInstance().Schedule(
            [self, pending]() { self->SetEmotion(pending.c_str()); });

        lv_anim_t reveal;
        lv_anim_init(&reveal);
        lv_anim_set_var(&reveal, self->transition_mask_);
        lv_anim_set_values(&reveal, LV_OPA_COVER, LV_OPA_TRANSP);
        lv_anim_set_duration(&reveal, 420);
        lv_anim_set_path_cb(&reveal, lv_anim_path_ease_in_out);
        lv_anim_set_exec_cb(&reveal, SetObjectOpacity);
        lv_anim_set_user_data(&reveal, self);
        lv_anim_set_completed_cb(&reveal, FinishFaceReveal);
        lv_anim_start(&reveal);
    }

    void StartSplashTransition() {
        if (transition_started_ || splash_ == nullptr)
            return;
        transition_started_ = true;

        // Decode the destination while it is hidden, then cover the complete
        // frame before swapping. A single-buffered SPI panel cannot safely show
        // a moving splash and an invalidating GIF at the same time.
        std::string pending;
        {
            std::lock_guard<std::mutex> guard(pending_emotion_mutex_);
            pending = pending_emotion_;
        }
        RestoreMochiFaces();
        SpiLcdDisplay::SetEmotion(pending.c_str());

        transition_mask_ = MakeBlock(lv_screen_active(), width_, height_, 0, 0, 0x000000, 0);
        lv_obj_set_style_opa(transition_mask_, LV_OPA_TRANSP, 0);
        lv_obj_move_foreground(transition_mask_);

        lv_anim_t cover;
        lv_anim_init(&cover);
        lv_anim_set_var(&cover, transition_mask_);
        lv_anim_set_values(&cover, LV_OPA_TRANSP, LV_OPA_COVER);
        lv_anim_set_duration(&cover, 280);
        lv_anim_set_path_cb(&cover, lv_anim_path_ease_in_out);
        lv_anim_set_exec_cb(&cover, SetObjectOpacity);
        lv_anim_set_user_data(&cover, this);
        lv_anim_set_completed_cb(&cover, SwapSplashToFace);
        lv_anim_start(&cover);
    }

    void RestoreMochiFaces() {
        if (!mochi_faces_)
            return;
        auto& themes = LvglThemeManager::GetInstance();
        auto* dark = themes.GetTheme("dark");
        auto* light = themes.GetTheme("light");
        dark->set_emoji_collection(mochi_faces_);
        light->set_emoji_collection(mochi_faces_);
        current_theme_ = dark;
    }

    static lv_obj_t* MakeBlock(lv_obj_t* parent, int w, int h, int x, int y, uint32_t color,
                               int radius) {
        auto* block = lv_obj_create(parent);
        lv_obj_set_size(block, w, h);
        lv_obj_set_pos(block, x, y);
        lv_obj_set_style_bg_color(block, lv_color_hex(color), 0);
        lv_obj_set_style_bg_opa(block, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(block, 0, 0);
        lv_obj_set_style_radius(block, radius, 0);
        lv_obj_set_style_pad_all(block, 0, 0);
        lv_obj_set_scrollbar_mode(block, LV_SCROLLBAR_MODE_OFF);
        return block;
    }

    lv_obj_t* MakeWave(int x, int y, bool left) {
        auto* wave = lv_arc_create(splash_);
        lv_obj_set_size(wave, 26, 48);
        lv_obj_set_pos(wave, x, y);
        lv_arc_set_bg_angles(wave, left ? 110 : 290, left ? 250 : 70);
        lv_arc_set_angles(wave, left ? 110 : 290, left ? 250 : 70);
        lv_obj_set_style_arc_width(wave, 2, LV_PART_MAIN);
        lv_obj_set_style_arc_width(wave, 2, LV_PART_INDICATOR);
        lv_obj_set_style_arc_color(wave, lv_color_hex(0x53F7D0), LV_PART_MAIN);
        lv_obj_set_style_arc_color(wave, lv_color_hex(0x53F7D0), LV_PART_INDICATOR);
        lv_obj_set_style_bg_opa(wave, LV_OPA_TRANSP, LV_PART_KNOB);
        lv_obj_remove_flag(wave, LV_OBJ_FLAG_CLICKABLE);
        return wave;
    }

    void AnimateWaiting() {
        if (splash_ == nullptr) {
            if (neutral_pending_.load() &&
                esp_timer_get_time() >= emotion_hold_until_us_.load()) {
                neutral_pending_.store(false);
                Application::GetInstance().Schedule([this]() { SetEmotion("neutral"); });
            }
            return;
        }
        ++tick_;
        // Ensure STARTING UP remains readable even when the network and OTA
        // stages complete unusually quickly.
        if (loading_phase_requested_ && !loading_phase_started_ &&
            esp_timer_get_time() - splash_started_us_ >= 1800 * 1000) {
            BeginLoadingPhase();
        }
        if (progress_ < target_progress_ && (ready_ || tick_ % 2 == 0)) {
            const int step = ready_ ? 6 : 1;
            progress_ = std::min(progress_ + step, target_progress_);
            if (progress_ > 0) {
                lv_obj_remove_flag(progress_fill_, LV_OBJ_FLAG_HIDDEN);
                lv_obj_set_width(progress_fill_, std::max(1, 292 * progress_ / 100));
            }
            char value[8];
            snprintf(value, sizeof(value), "%d%%", progress_);
            lv_label_set_text(progress_text_, value);
        }
        if (ready_ && progress_ == 100) {
            ++completion_ticks_;
            if (completion_ticks_ >= 3)
                StartSplashTransition();
        }
    }
};

class TouchDriver {
public:
    TouchDriver() : dev_(nullptr) {}

    bool Init(i2c_master_bus_handle_t bus, uint8_t addr) {
        i2c_device_config_t cfg = {
            .device_address = addr,
            .scl_speed_hz = 400000,
            .scl_wait_us = 0,
        };
        return i2c_master_bus_add_device(bus, &cfg, &dev_) == ESP_OK;
    }

    bool Read(bool& touched, uint16_t& x, uint16_t& y) {
        touched = false;
        x = y = 0;
        if (!dev_)
            return false;

        uint8_t reg = 0x02;
        uint8_t buf[5];
        if (i2c_master_transmit_receive(dev_, &reg, 1, buf, 5, 50) != ESP_OK)
            return false;

        uint8_t points = buf[0] & 0x0F;
        if (points == 0)
            return true;

        touched = true;
        x = ((buf[1] & 0x0F) << 8) | buf[2];
        y = ((buf[3] & 0x0F) << 8) | buf[4];
        return true;
    }

private:
    i2c_master_dev_handle_t dev_;
};

class FreenoveESP32S3Display : public WifiBoard {
private:
    const char* GetWifiSsidPrefix() const override { return "Wisio 1"; }
    bool AppendMacToWifiSsid() const override { return false; }

    Button boot_button_;
    LcdDisplay* display_;
    i2c_master_bus_handle_t codec_i2c_bus_;
    TouchDriver touch_;
    AdcBatteryMonitor* adc_battery_monitor_;

    void InitializeBatteryMonitor() {
        adc_battery_monitor_ =
            new AdcBatteryMonitor(ADC_UNIT_1, ADC_CHANNEL_8, 200000, 200000, GPIO_NUM_NC);
    }

    static void TouchTask(void* arg) {
        auto* self = static_cast<FreenoveESP32S3Display*>(arg);
        auto& app = Application::GetInstance();

        uint32_t last_tap = 0;
        uint32_t down_start = 0;
        bool down = false;

        while (true) {
            bool t;
            uint16_t x, y;
            self->touch_.Read(t, x, y);

            uint32_t now = esp_timer_get_time() / 1000;

            if (t) {
                if (!down) {
                    down = true;
                    down_start = now;
                }
            }

            if (!t && down) {
                down = false;

                uint32_t press = now - down_start;

                // long tap
                if (press > 3000) {
                    self->EnterWifiConfigMode();
                } else {
                    // A tap during activation would force Idle before the
                    // WebSocket protocol exists, leaving a face that appears
                    // ready but cannot listen.
                    auto state = app.GetDeviceState();
                    if (state == kDeviceStateStarting || state == kDeviceStateActivating ||
                        state == kDeviceStateWifiConfiguring) {
                        last_tap = 0;
                        continue;
                    }
                    // double tap
                    if (now - last_tap < 250) {
                        app.StartListening();
                        last_tap = 0;
                    } else {
                        // single tap
                        app.ToggleChatState();
                        last_tap = now;
                    }
                }
            }

            vTaskDelay(pdMS_TO_TICKS(50));
        }
    }

    void InitializeTouch() {
        if (!touch_.Init(codec_i2c_bus_, 0x38))
            return;
        xTaskCreatePinnedToCore(TouchTask, "touch_task", 4096, this, 5, nullptr, 0);
    }

    void InitializeI2c() {
        i2c_master_bus_config_t i2c_bus_cfg = {
            .i2c_port = AUDIO_CODEC_I2C_NUM,
            .sda_io_num = AUDIO_CODEC_I2C_SDA_PIN,
            .scl_io_num = AUDIO_CODEC_I2C_SCL_PIN,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .intr_priority = 0,
            .trans_queue_depth = 0,
            .flags =
                {
                    .enable_internal_pullup = 1,
                },
        };
        ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_bus_cfg, &codec_i2c_bus_));
    }

    void InitializeSpi() {
        spi_bus_config_t buscfg = {};
        buscfg.mosi_io_num = DISPLAY_MOSI_PIN;
        buscfg.miso_io_num = DISPLAY_MIS0_PIN;
        buscfg.sclk_io_num = DISPLAY_SCK_PIN;
        buscfg.quadwp_io_num = GPIO_NUM_NC;
        buscfg.quadhd_io_num = GPIO_NUM_NC;
        buscfg.max_transfer_sz = DISPLAY_WIDTH * DISPLAY_HEIGHT * sizeof(uint16_t);
        ESP_ERROR_CHECK(spi_bus_initialize(LCD_SPI_HOST, &buscfg, SPI_DMA_CH_AUTO));
    }

    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting) {
                EnterWifiConfigMode();
                return;
            }
            if (app.GetDeviceState() == kDeviceStateActivating)
                return;
            app.ToggleChatState();
        });
    }

    void InitializeLcdDisplay() {
        esp_lcd_panel_io_handle_t panel_io = nullptr;
        esp_lcd_panel_handle_t panel = nullptr;
        // 液晶屏控制IO初始化
        ESP_LOGD(TAG, "Install panel IO");
        esp_lcd_panel_io_spi_config_t io_config = {};
        io_config.cs_gpio_num = DISPLAY_CS_PIN;
        io_config.dc_gpio_num = DISPLAY_DC_PIN;
        io_config.spi_mode = DISPLAY_SPI_MODE;
        io_config.pclk_hz = DISPLAY_SPI_SCLK_HZ;
        io_config.trans_queue_depth = 10;
        io_config.lcd_cmd_bits = 8;
        io_config.lcd_param_bits = 8;
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(LCD_SPI_HOST, &io_config, &panel_io));

        // 初始化液晶屏驱动芯片
        ESP_LOGD(TAG, "Install LCD driver");
        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = DISPLAY_RST_PIN;
        panel_config.rgb_ele_order = DISPLAY_RGB_ORDER;
        panel_config.bits_per_pixel = 16;
        ESP_ERROR_CHECK(esp_lcd_new_panel_ili9341(panel_io, &panel_config, &panel));
        ESP_LOGI(TAG, "Install LCD driver ILI9341");
        esp_lcd_panel_reset(panel);

        esp_lcd_panel_init(panel);
        esp_lcd_panel_invert_color(panel, DISPLAY_INVERT_COLOR);
        esp_lcd_panel_swap_xy(panel, DISPLAY_SWAP_XY);
        esp_lcd_panel_mirror(panel, DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y);
        display_ = new EchoCoreLcdDisplay(panel_io, panel, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                          DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y, DISPLAY_MIRROR_X,
                                          DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY);
    }

    void InitializeTools() {}

public:
    FreenoveESP32S3Display() : boot_button_(BOOT_BUTTON_GPIO) {
        // Hold the physical backlight off from the first instruction. The LCD
        // controller powers up before LVGL has drawn its first complete frame;
        // leaving this pin floating briefly exposes that uninitialised frame as
        // a white/black flash on cold boot.
        gpio_set_direction(DISPLAY_BACKLIGHT_PIN, GPIO_MODE_OUTPUT);
        gpio_set_level(DISPLAY_BACKLIGHT_PIN, DISPLAY_BACKLIGHT_OUTPUT_INVERT ? 1 : 0);
        // Keep the OTA/WebSocket values provisioned through the Wi-Fi portal.
        // Overwriting them here ties a release to the developer's LAN address
        // and prevents a device from recovering after the user's IP changes.
        InitializeI2c();
        InitializeBatteryMonitor();
        InitializeSpi();
        InitializeLcdDisplay();
        InitializeTouch();
        InitializeButtons();
        InitializeTools();
        // SetupUI turns the backlight on only after its first complete frame.
    }

    void StartNetwork() override {
        WifiBoard::StartNetwork();
        // Limit WiFi TX power to 18 dBm (72 * 0.25 dBm) to prevent USB power dips
        // when LCD backlight, audio PA, and WiFi radio draw current together.
        esp_wifi_set_max_tx_power(72);
    }

    virtual Led* GetLed() override {
        static SingleLed led(BUILTIN_LED_GPIO);
        return &led;
    }

    virtual AudioCodec* GetAudioCodec() override {
        static Es8311AudioCodec audio_codec(
            codec_i2c_bus_, AUDIO_CODEC_I2C_NUM, AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_GPIO_MCLK, AUDIO_I2S_GPIO_BCLK, AUDIO_I2S_GPIO_WS, AUDIO_I2S_GPIO_DOUT,
            AUDIO_I2S_GPIO_DIN, AUDIO_CODEC_PA_PIN, AUDIO_CODEC_ES8311_ADDR, true, true);
        return &audio_codec;
    }

    virtual Display* GetDisplay() override { return display_; }

    virtual Backlight* GetBacklight() override {
        static PwmBacklight backlight(DISPLAY_BACKLIGHT_PIN, DISPLAY_BACKLIGHT_OUTPUT_INVERT);
        return &backlight;
    }

    virtual bool GetBatteryLevel(int& level, bool& charging, bool& discharging) override {
        charging = adc_battery_monitor_->IsCharging();
        discharging = adc_battery_monitor_->IsDischarging();
        level = adc_battery_monitor_->GetBatteryLevel();
        return true;
    }
};

DECLARE_BOARD(FreenoveESP32S3Display);
