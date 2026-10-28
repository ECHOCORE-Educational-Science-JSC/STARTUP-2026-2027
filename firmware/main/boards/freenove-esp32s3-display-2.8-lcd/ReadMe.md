# Freenove ESP32-S3 ESP32 S3 Capacitive Touch Display CYD WiFi BT, 2.8 Inch 240x320 IPS Screen

[product](https://store.freenove.com/products/fnk0104)

Official github: [freenove-esp32s3-display-2.8-lcd](https://github.com/Freenove/Freenove_ESP32_S3_Display)

Likely the same hardware design as [LCD wiki ES3C28P/ES3N28P](https://www.lcdwiki.com/2.8inch_ESP32-S3_Display)

## Wisio external power and wake phrase — 18/10/2026

This Wisio configuration uses continuous external USB power, with no battery
telemetry. The board does not create an ADC battery monitor, register a charge
callback or report a supported battery capability. Battery percentages, low
battery sounds/popups and automatic charge-mode suspension therefore cannot
activate on this board. GPIO assignments for audio, LCD and touch are unchanged.

This software setting does not disable the physical charger IC. Shared charging
support remains available to other board implementations with batteries.

For the current configured project, run this in an ESP-IDF terminal from the firmware directory:

```powershell
python scripts/configure_wisio_wake.py
idf.py build
```

The configuration tool preserves local settings and uses ESP-IDF Kconfig to select English MultiNet5 Q8 with `HEY WISIO`, displayed as `Hey Wisio`, at a 70% threshold. The asset builder supplies explicit phonemes for “wee-zee-oh”, “wiz-ee-oh”, and “wiss-ee-oh”, so the coined name is not left to English spelling/G2P guesses. This profile requires matching phoneme assets and excludes the large automatic G2P dictionary from the app. Other custom commands keep their existing registration. The canonical fresh-build alternative is:

```powershell
python scripts/build.py freenove-esp32s3-display-2.8-lcd --name freenove-esp32s3-display-2.8-lcd --language vi-VN --wake-word hey-wisio
```

Flash the complete project, including `generated_assets.bin`. The phrase is recognized locally from standby, with recognition disabled during listening. This uses custom MultiNet command recognition, not a separately trained WakeNet model. Physical tests with children's voices and background noise are still required; configuration and host tests do not establish wake accuracy. See [Espressif's custom-command documentation](https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/speech_command_recognition/README.html).

### Diagnosing standby wake — 19/10/2026

Flash the app and assets together after changing the MultiNet version. An app-only
update leaves the old speech model on the device. In the ESP-IDF monitor, standby
should show `Wake ready: Hey Wisio, model=mn5q8_en, threshold=0.70`. Every ten seconds,
`Wake listening: mic peak=... (10s)` confirms that microphone frames actually reach
the recognizer. A successful match logs `Custom wake word detected` followed by
`Application: Wake word detected` and the connecting/listening state transition.
Missing `Wake ready` means initialization/state needs investigation; no listening
summary after it means audio capture/AFE needs investigation. A changing peak
without a match means pronunciation/recognition still needs physical testing.
The decoder and partial input are cleared each time wake is re-armed from standby;
repeated enable calls while already running do not discard a phrase in progress.
On this microphone-only codec, MultiNet is not advertised as playback-safe wake
detection: it is disabled while the robot speaks/plays music, then re-enabled in
standby. This keeps the robot's own greeting from being treated as a user wake
phrase. Boards with a real speaker-reference input retain their AEC wake support.
