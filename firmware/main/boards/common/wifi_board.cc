#include "wifi_board.h"

#include "application.h"
#include "assets/lang_config.h"
#include "display.h"
#include "settings.h"
#include "system_info.h"

#include <esp_log.h>
#include <esp_mac.h>
#include <esp_network.h>
#include <esp_wifi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <memory>
#include <new>
#include <utility>

#include <material_symbols.h>
#include <ssid_manager.h>
#include <wifi_manager.h>
#include <wifi_station.h>
#ifdef CONFIG_USE_ESP_BLUFI_WIFI_PROVISIONING
#include "blufi.h"
#endif

static const char* TAG = "WifiBoard";

// Connection timeout in seconds
static constexpr int CONNECT_TIMEOUT_SEC = 12;

WifiBoard::WifiBoard() {
    // Create connection timeout timer
    esp_timer_create_args_t timer_args = {.callback = OnWifiConnectTimeout,
                                          .arg = this,
                                          .dispatch_method = ESP_TIMER_TASK,
                                          .name = "wifi_connect_timer",
                                          .skip_unhandled_events = false};
    ESP_ERROR_CHECK(esp_timer_create(&timer_args, &connect_timer_));
}

WifiBoard::~WifiBoard() {
    if (connect_timer_) {
        esp_timer_stop(connect_timer_);
        esp_timer_delete(connect_timer_);
    }
}

std::string WifiBoard::GetBoardType() { return "wifi"; }

void WifiBoard::StartNetwork() {
    auto& wifi_manager = WifiManager::GetInstance();

    // Initialize WiFi manager
    WifiManagerConfig config;
    config.ssid_prefix = GetWifiSsidPrefix();
    config.append_mac_to_ap_ssid = AppendMacToWifiSsid();
    config.language = Lang::CODE;
    config.show_ota_config = true;
    config.show_sleep_config = true;

    // Set a DHCP hostname so the router shows a friendly name instead of "espressif".
    // Uses the same "<prefix>-<last 2 MAC bytes>" scheme as the config AP SSID.
    uint8_t mac[6];
    if (esp_read_mac(mac, ESP_MAC_WIFI_STA) == ESP_OK) {
        char hostname[32];
        snprintf(hostname, sizeof(hostname), "%s-%02X%02X", config.ssid_prefix.c_str(), mac[4],
                 mac[5]);
        config.station_hostname = hostname;
    }
    wifi_manager.Initialize(config);

    const int8_t max_tx_power = GetWifiMaxTxPower();
    if (max_tx_power != 0) {
        esp_err_t power_result = esp_wifi_set_max_tx_power(max_tx_power);
        if (power_result != ESP_OK) {
            ESP_LOGW(TAG, "Failed to set WiFi TX power to %d: %s", max_tx_power,
                     esp_err_to_name(power_result));
        }
    }

    // Set unified event callback - forward to NetworkEvent with SSID data
    wifi_manager.SetEventCallback([this](WifiEvent event, const std::string& data) {
        switch (event) {
            case WifiEvent::Scanning:
                OnNetworkEvent(NetworkEvent::Scanning);
                break;
            case WifiEvent::Connecting:
                OnNetworkEvent(NetworkEvent::Connecting, data);
                break;
            case WifiEvent::Connected:
                OnNetworkEvent(NetworkEvent::Connected, data);
                break;
            case WifiEvent::Disconnected:
                OnNetworkEvent(NetworkEvent::Disconnected);
                break;
            case WifiEvent::ConfigModeEnter:
                OnNetworkEvent(NetworkEvent::WifiConfigModeEnter);
                break;
            case WifiEvent::ConfigModeExit:
                OnNetworkEvent(NetworkEvent::WifiConfigModeExit);
                break;
        }
    });

    // Try to connect or enter config mode
    TryWifiConnect();
}

void WifiBoard::TryWifiConnect() {
    auto& ssid_manager = SsidManager::GetInstance();
    bool have_ssid = !ssid_manager.GetSsidList().empty();

    if (have_ssid) {
        // Start connection attempt with timeout
        ESP_LOGI(TAG, "Starting WiFi connection attempt");
        ArmWifiConnectTimeout();
        WifiManager::GetInstance().StartStation();
    } else {
        // No SSID configured, enter config mode
        // Open provisioning immediately; never block startup for a version label.
        StartWifiConfigMode();
    }
}

void WifiBoard::OnNetworkEvent(NetworkEvent event, const std::string& data) {
    switch (event) {
        case NetworkEvent::Connected:
            // Stop timeout timer
            CancelWifiConnectTimeout();
            {
                std::lock_guard<std::mutex> lock(wifi_state_mutex_);
                if (in_config_mode_ && config_task_pending_)
                    return;
                in_config_mode_ = false;
            }
#ifdef CONFIG_USE_ESP_BLUFI_WIFI_PROVISIONING
            // make sure blufi resources has been released
            Blufi::GetInstance().deinit();
#endif
            ESP_LOGI(TAG, "Connected to WiFi: %s", data.c_str());
            break;
        case NetworkEvent::Scanning:
            ESP_LOGI(TAG, "WiFi scanning");
            break;
        case NetworkEvent::Connecting:
            ESP_LOGI(TAG, "WiFi connecting to %s", data.c_str());
            break;
        case NetworkEvent::Disconnected:
            ESP_LOGW(TAG, "WiFi disconnected");
            ArmWifiConnectTimeout();
            break;
        case NetworkEvent::WifiConfigModeEnter:
            wifi_config_generation_.fetch_add(1);
            ESP_LOGI(TAG, "WiFi config mode entered");
            CancelWifiConnectTimeout();
            {
                std::lock_guard<std::mutex> lock(wifi_state_mutex_);
                in_config_mode_ = true;
            }
            break;
        case NetworkEvent::WifiConfigModeExit:
            wifi_config_generation_.fetch_add(1);
            ESP_LOGI(TAG, "WiFi config mode exited");
            {
                std::lock_guard<std::mutex> lock(wifi_state_mutex_);
                in_config_mode_ = false;
            }
            // Avoid re-entering WifiManager during its mode transition.
            Application::GetInstance().Schedule([this]() {
                Application::GetInstance().GetAudioService().ResetDecoder();
                TryWifiConnect();
            });
            break;
        default:
            break;
    }

    // Notify external callback if set
    if (network_event_callback_) {
        network_event_callback_(event, data);
    }
}

void WifiBoard::SetNetworkEventCallback(NetworkEventCallback callback) {
    network_event_callback_ = std::move(callback);
}

void WifiBoard::ArmWifiConnectTimeout() {
    std::lock_guard<std::mutex> lock(wifi_state_mutex_);
    if (in_config_mode_ || config_task_pending_ || connect_deadline_us_ != 0)
        return;
    connect_deadline_us_ = esp_timer_get_time() + CONNECT_TIMEOUT_SEC * 1000000LL;
    esp_timer_stop(connect_timer_);
    const auto err = esp_timer_start_once(connect_timer_, CONNECT_TIMEOUT_SEC * 1000000ULL);
    if (err != ESP_OK) {
        connect_deadline_us_ = 0;
        ESP_LOGE(TAG, "Cannot arm WiFi deadline: %s", esp_err_to_name(err));
    }
}

void WifiBoard::CancelWifiConnectTimeout() {
    std::lock_guard<std::mutex> lock(wifi_state_mutex_);
    connect_deadline_us_ = 0;
    esp_timer_stop(connect_timer_);
}

void WifiBoard::OnWifiConnectTimeout(void* arg) {
    auto* board = static_cast<WifiBoard*>(arg);
    int64_t deadline;
    {
        std::lock_guard<std::mutex> lock(board->wifi_state_mutex_);
        deadline = board->connect_deadline_us_;
        if (deadline == 0 || esp_timer_get_time() < deadline)
            return;
    }
    // No blocking Wi-Fi stop, event-handler teardown, or UI on the timer task.
    board->QueueWifiConfigMode(deadline);
}

void WifiBoard::StartWifiConfigMode() { QueueWifiConfigMode(); }

void WifiBoard::QueueWifiConfigMode(int64_t expected_deadline_us) {
    {
        std::lock_guard<std::mutex> lock(wifi_state_mutex_);
        if (in_config_mode_ || config_task_pending_)
            return;
        if (expected_deadline_us != 0 && (connect_deadline_us_ != expected_deadline_us ||
                                          esp_timer_get_time() < expected_deadline_us))
            return;
        config_request_deadline_us_ = expected_deadline_us;
        config_task_pending_ = true;
    }
    if (xTaskCreate(
            [](void* arg) {
                static_cast<WifiBoard*>(arg)->RunWifiConfigTransition();
                vTaskDelete(nullptr);
            },
            "wifi_config", 4096, this, 2, nullptr) != pdPASS) {
        std::lock_guard<std::mutex> lock(wifi_state_mutex_);
        config_task_pending_ = false;
        ESP_LOGE(TAG, "Cannot create WiFi provisioning task; retrying");
        if (connect_deadline_us_ == 0)
            connect_deadline_us_ = esp_timer_get_time();
        esp_timer_stop(connect_timer_);
        esp_timer_start_once(connect_timer_, 1000000);
    }
}

void WifiBoard::RunWifiConfigTransition() {
    auto& wifi_manager = WifiManager::GetInstance();
    int64_t deadline;
    {
        std::lock_guard<std::mutex> lock(wifi_state_mutex_);
        deadline = config_request_deadline_us_;
    }
    // Never tear down the network underneath an in-progress firmware write.
    const auto state = Application::GetInstance().GetDeviceState();
    if (state == kDeviceStateUpgrading || state == kDeviceStateFatalError) {
        std::lock_guard<std::mutex> lock(wifi_state_mutex_);
        config_task_pending_ = false;
        if (state == kDeviceStateUpgrading && connect_deadline_us_ != 0)
            esp_timer_start_once(connect_timer_, 1000000);
        return;
    }
    // Manager methods take their own lock; never call them while holding ours.
    const bool connected = wifi_manager.IsConnected();
    {
        std::lock_guard<std::mutex> lock(wifi_state_mutex_);
        if (deadline != 0 &&
            (connected || connect_deadline_us_ != deadline || esp_timer_get_time() < deadline)) {
            config_task_pending_ = false;
            return;
        }
        in_config_mode_ = true;
        connect_deadline_us_ = 0;
        esp_timer_stop(connect_timer_);
    }
    ESP_LOGW(TAG, "Opening WiFi setup%s", deadline ? " after 12s without a connection" : "");
    Application::GetInstance().Schedule([this, deadline]() {
        auto& app = Application::GetInstance();
        const auto state = app.GetDeviceState();
        // Live conversation states return through idle before provisioning.
        if (state == kDeviceStateConnecting || state == kDeviceStateListening ||
            state == kDeviceStateSpeaking || state == kDeviceStateNotifying) {
            app.SetDeviceState(kDeviceStateIdle);
        }
        app.ResetProtocol();
        app.SetDeviceState(kDeviceStateWifiConfiguring);
        GetDisplay()->ShowWifiSetup(
            deadline ? "Không kết nối được Wi-Fi.\nĐang mở trang cấu hình..."
                     : "Đang mở cấu hình Wi-Fi...\nDùng điện thoại để kết nối Wisio.");
    });
    wifi_manager.StopStation();
#ifdef CONFIG_USE_HOTSPOT_WIFI_PROVISIONING
    wifi_manager.StartConfigAp();
    Application::GetInstance().Schedule([this, deadline]() {
        auto& wifi = WifiManager::GetInstance();
        if (!wifi.IsConfigMode())
            return;
        std::string hint = deadline ? "Không kết nối được Wi-Fi.\n" : "Cấu hình Wi-Fi cho Wisio\n";
        hint += "Trên điện thoại, kết nối:\n" + wifi.GetApSsid();
        hint += "\nMở: " + wifi.GetApWebUrl();
        hint += "\nNhập tên mạng và mật mã.";
        // Play the bundled offline provisioning announcement exactly once.
        auto& app = Application::GetInstance();
        auto sound = Lang::Sounds::OGG_WIFICONFIG;
#if CONFIG_LANGUAGE_VI_VN
        if (deadline != 0)
            sound = Lang::Sounds::OGG_WIFICONFIG_FAILED;
#endif
        app.Alert(Lang::Strings::WIFI_CONFIG_MODE, hint.c_str(), "gear", {});
        GetDisplay()->ShowWifiSetup(hint);
        // ResetProtocol's scheduled cleanup precedes this job. Long speech
        // feeds a bounded audio queue on a worker, never on the UI/main task.
        app.Schedule([this, sound]() { StartWifiSetupNotice(sound); });
    });
#elif CONFIG_USE_ESP_BLUFI_WIFI_PROVISIONING
    Blufi::GetInstance().init();
    Application::GetInstance().Schedule([]() {
        Application::GetInstance().Alert(Lang::Strings::WIFI_CONFIG_MODE,
                                         Lang::Strings::ENTERING_WIFI_CONFIG_MODE, "gear",
                                         Lang::Sounds::OGG_WIFICONFIG);
    });
#endif
    bool connect_requested;
    {
        std::lock_guard<std::mutex> lock(wifi_state_mutex_);
        config_task_pending_ = false;
        connect_requested = !in_config_mode_;
    }
    if (connect_requested)
        Application::GetInstance().Schedule([this]() { TryWifiConnect(); });
}

void WifiBoard::StartWifiSetupNotice(std::string_view sound) {
    auto& app = Application::GetInstance();
    if (!IsInWifiConfigMode() || app.GetDeviceState() != kDeviceStateWifiConfiguring)
        return;
    struct Notice {
        WifiBoard* board;
        std::string_view sound;
        uint32_t generation;
    };
    auto* notice = new (std::nothrow) Notice{this, sound, wifi_config_generation_.load()};
    if (!notice)
        return;  // The visual instructions are already visible.
    if (xTaskCreate(
            [](void* arg) {
                std::unique_ptr<Notice> owned(static_cast<Notice*>(arg));
                auto& app = Application::GetInstance();
                app.GetAudioService().PlaySound(owned->sound, [&]() {
                    return owned->board->wifi_config_generation_.load() == owned->generation &&
                           !app.IsChargingMode();
                });
                owned.reset();
                vTaskDelete(nullptr);
            },
            "wifi_notice", 4096, notice, 2, nullptr) != pdPASS) {
        delete notice;
        ESP_LOGE(TAG, "WiFi speech unavailable; setup instructions remain visible");
    }
}

void WifiBoard::EnterWifiConfigMode() {
    const auto state = Application::GetInstance().GetDeviceState();
    if (state == kDeviceStateUpgrading || state == kDeviceStateFatalError)
        return;
    StartWifiConfigMode();
}

bool WifiBoard::IsInWifiConfigMode() const { return WifiManager::GetInstance().IsConfigMode(); }

NetworkInterface* WifiBoard::GetNetwork() {
    static EspNetwork network;
    return &network;
}

const char* WifiBoard::GetNetworkStateIcon() {
    auto& wifi = WifiManager::GetInstance();

    if (wifi.IsConfigMode()) {
        return MATERIAL_SYMBOLS_WIFI;
    }
    if (!wifi.IsConnected()) {
        return MATERIAL_SYMBOLS_WIFI_OFF;
    }

    int rssi = wifi.GetRssi();
    if (rssi >= -65) {
        return MATERIAL_SYMBOLS_WIFI;
    } else if (rssi >= -75) {
        return MATERIAL_SYMBOLS_WIFI_2_BAR;
    }
    return MATERIAL_SYMBOLS_WIFI_1_BAR;
}

std::string WifiBoard::GetBoardJson() {
    auto& wifi = WifiManager::GetInstance();
    std::string json = R"({"type":")" + std::string(BOARD_TYPE) + R"(",)";
    json += R"("name":")" + std::string(BOARD_NAME) + R"(",)";
    json += R"("manufacturer":")" + std::string(BOARD_MANUFACTURER) + R"(",)";

    if (!wifi.IsConfigMode()) {
        json += R"("ssid":")" + wifi.GetSsid() + R"(",)";
        json += R"("rssi":)" + std::to_string(wifi.GetRssi()) + R"(,)";
        json += R"("channel":)" + std::to_string(wifi.GetChannel()) + R"(,)";
        json += R"("ip":")" + wifi.GetIpAddress() + R"(",)";
    }

    json += R"("mac":")" + SystemInfo::GetMacAddress() + R"("})";
    return json;
}

void WifiBoard::SetPowerSaveLevel(PowerSaveLevel level) {
    WifiPowerSaveLevel wifi_level;
    switch (level) {
        case PowerSaveLevel::LOW_POWER:
            wifi_level = WifiPowerSaveLevel::LOW_POWER;
            break;
        case PowerSaveLevel::BALANCED:
            wifi_level = WifiPowerSaveLevel::BALANCED;
            break;
        case PowerSaveLevel::PERFORMANCE:
        default:
            wifi_level = WifiPowerSaveLevel::PERFORMANCE;
            break;
    }
    WifiManager::GetInstance().SetPowerSaveLevel(wifi_level);
}

std::string WifiBoard::GetDeviceStatusJson() {
    auto& board = Board::GetInstance();
    auto root = cJSON_CreateObject();

    // Audio speaker
    auto audio_speaker = cJSON_CreateObject();
    if (auto codec = board.GetAudioCodec()) {
        cJSON_AddNumberToObject(audio_speaker, "volume", codec->output_volume());
    }
    cJSON_AddItemToObject(root, "audio_speaker", audio_speaker);

    // Screen
    auto screen = cJSON_CreateObject();
    if (auto backlight = board.GetBacklight()) {
        cJSON_AddNumberToObject(screen, "brightness", backlight->brightness());
    }
    if (auto display = board.GetDisplay(); display && display->height() > 64) {
        if (auto theme = display->GetTheme()) {
            cJSON_AddStringToObject(screen, "theme", theme->name().c_str());
        }
    }
    cJSON_AddItemToObject(root, "screen", screen);

    // Battery
    int level = 0;
    bool charging = false, discharging = false;
    if (board.GetBatteryLevel(level, charging, discharging)) {
        auto battery = cJSON_CreateObject();
        cJSON_AddNumberToObject(battery, "level", level);
        cJSON_AddBoolToObject(battery, "charging", charging);
        cJSON_AddItemToObject(root, "battery", battery);
    }

    // Network
    auto& wifi = WifiManager::GetInstance();
    auto network = cJSON_CreateObject();
    cJSON_AddStringToObject(network, "type", "wifi");
    cJSON_AddStringToObject(network, "ssid", wifi.GetSsid().c_str());
    int rssi = wifi.GetRssi();
    const char* signal = rssi >= -60 ? "strong" : (rssi >= -70 ? "medium" : "weak");
    cJSON_AddStringToObject(network, "signal", signal);
    cJSON_AddItemToObject(root, "network", network);

    // Chip temperature
    float temp = 0.0f;
    if (board.GetTemperature(temp)) {
        auto chip = cJSON_CreateObject();
        cJSON_AddNumberToObject(chip, "temperature", temp);
        cJSON_AddItemToObject(root, "chip", chip);
    }

    auto str = cJSON_PrintUnformatted(root);
    std::string result(str);
    cJSON_free(str);
    cJSON_Delete(root);
    return result;
}
