# Freenove ESP32-S3 ESP32 S3 Capacitive Touch Display CYD WiFi BT, 2.8 Inch 240x320 IPS Screen

[product](https://store.freenove.com/products/fnk0104)

Official github: [freenove-esp32s3-display-2.8-lcd](https://github.com/Freenove/Freenove_ESP32_S3_Display)

Likely the same hardware design as [LCD wiki ES3C28P/ES3N28P](https://www.lcdwiki.com/2.8inch_ESP32-S3_Display)

## Wisio charging and wake phrase

The [official 2.8-inch schematic](https://github.com/Freenove/Freenove_ESP32_S3_Display/blob/main/Schematic/2.8inch_ESP32-S3_Display_Schematic.pdf) does **not** connect TP4054 `CHRG` to the MCU. `CHRG` goes through R11 (10 kOhm) to ground; GPIO3 is expansion IO. The earlier GPIO3/pull-up claim was incorrect. `BATTERY_CHARGING_GPIO` therefore stays `GPIO_NUM_NC` and automatic charging shutdown is disabled on the stock board. The robot remains usable on battery or USB; voltage recovery and an unused GPIO cannot turn its screen/audio off.

The charging suspend implementation is retained for hardware with a real charge-status input: it suspends microphone capture, wake recognition, speaker output, music and conversation and turns off the LCD. The stock FNK0104 board cannot activate it automatically. Reliable charging detection requires a verified status connection and compatible pull-up circuitry, or a separate charger/power controller reporting status. Do not simply assign GPIO3 or wire CHRG without reviewing its existing pull-down and voltage levels. USB host activity is not a battery-charging signal, and a wall charger may not provide USB data activity.

For the current configured project, run this in an ESP-IDF terminal from the firmware directory:

```powershell
python scripts/configure_wisio_wake.py
idf.py build
```

The configuration tool preserves local settings and uses ESP-IDF Kconfig to select English MultiNet6 with `HEY WISIO`, displayed as `Hey Wisio`, at a 70% threshold. The canonical fresh-build alternative is:

```powershell
python scripts/build.py freenove-esp32s3-display-2.8-lcd --name freenove-esp32s3-display-2.8-lcd --language vi-VN --wake-word hey-wisio
```

Flash the complete project, including `generated_assets.bin`. The phrase is recognized locally from standby, with recognition disabled during listening and charging. This uses custom MultiNet command recognition, not a separately trained WakeNet model. Physical tests with children's voices and background noise are still required; configuration and host tests do not establish wake accuracy. See [Espressif's custom-command documentation](https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/speech_command_recognition/README.html).
