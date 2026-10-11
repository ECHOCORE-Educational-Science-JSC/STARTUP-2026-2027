#ifndef ADC_BATTERY_MONITOR_H
#define ADC_BATTERY_MONITOR_H

#include <driver/gpio.h>
#include <esp_timer.h>
#include <adc_battery_estimation.h>
#include <atomic>
#include <functional>
#include "charging_status_filter.h"

class AdcBatteryMonitor {
public:
    AdcBatteryMonitor(adc_unit_t adc_unit, adc_channel_t adc_channel, float upper_resistor,
                      float lower_resistor, gpio_num_t charging_pin = GPIO_NUM_NC,
                      bool charging_active_low = false);
    ~AdcBatteryMonitor();

    bool IsCharging();
    bool IsDischarging();
    bool HasChargingStatusSignal() const { return charging_pin_ != GPIO_NUM_NC; }
    uint8_t GetBatteryLevel();

    void OnChargingStatusChanged(std::function<void(bool)> callback);

private:
    gpio_num_t charging_pin_;
    bool charging_active_low_;
    adc_battery_estimation_handle_t adc_battery_estimation_handle_ = nullptr;
    esp_timer_handle_t timer_handle_ = nullptr;
    std::atomic<bool> is_charging_{false};
    ChargingStatusFilter charging_filter_;
    std::function<void(bool)> on_charging_status_changed_;

    void CheckBatteryStatus();
};

#endif // ADC_BATTERY_MONITOR_H
