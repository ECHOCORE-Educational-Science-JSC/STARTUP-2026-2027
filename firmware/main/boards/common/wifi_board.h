#ifndef WIFI_BOARD_H
#define WIFI_BOARD_H

#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/event_groups.h>
#include <atomic>
#include <mutex>
#include <string_view>
#include "board.h"

class WifiBoard : public Board {
protected:
    esp_timer_handle_t connect_timer_ = nullptr;
    bool in_config_mode_ = false;
    std::mutex wifi_state_mutex_;
    int64_t connect_deadline_us_ = 0;
    int64_t config_request_deadline_us_ = 0;
    bool config_task_pending_ = false;
    std::atomic<uint32_t> wifi_config_generation_{0};
    NetworkEventCallback network_event_callback_ = nullptr;

    virtual const char* GetWifiSsidPrefix() const { return "Wisio"; }
    virtual bool AppendMacToWifiSsid() const { return true; }
    // ESP-IDF units are 0.25 dBm. Zero keeps the configured/default value.
    // Boards with a tight power budget can cap TX before station/AP startup.
    virtual int8_t GetWifiMaxTxPower() const { return 0; }

    virtual std::string GetBoardJson() override;

    /**
     * Handle network event (called from WiFi manager callbacks)
     * @param event The network event type
     * @param data Additional data (e.g., SSID for Connecting/Connected events)
     */
    void OnNetworkEvent(NetworkEvent event, const std::string& data = "");

    /**
     * Start WiFi connection attempt
     */
    void TryWifiConnect();

    /**
     * Enter WiFi configuration mode
     */
    void StartWifiConfigMode();
    void ArmWifiConnectTimeout();
    void CancelWifiConnectTimeout();
    void QueueWifiConfigMode(int64_t expected_deadline_us = 0);
    void RunWifiConfigTransition();
    void StartWifiSetupNotice(std::string_view sound);

    /**
     * WiFi connection timeout callback
     */
    static void OnWifiConnectTimeout(void* arg);

public:
    WifiBoard();
    virtual ~WifiBoard();

    virtual std::string GetBoardType() override;

    /**
     * Start network connection asynchronously
     * This function returns immediately. Network events are notified through the callback set by
     * SetNetworkEventCallback().
     */
    virtual void StartNetwork() override;

    virtual NetworkInterface* GetNetwork() override;
    virtual void SetNetworkEventCallback(NetworkEventCallback callback) override;
    virtual const char* GetNetworkStateIcon() override;
    virtual void SetPowerSaveLevel(PowerSaveLevel level) override;
    virtual AudioCodec* GetAudioCodec() override { return nullptr; }
    virtual std::string GetDeviceStatusJson() override;

    /**
     * Enter WiFi configuration mode (thread-safe, can be called from any task)
     */
    void EnterWifiConfigMode();

    /**
     * Check if in WiFi config mode
     */
    bool IsInWifiConfigMode() const;
};

#endif  // WIFI_BOARD_H
