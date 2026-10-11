# Third-party notices

Wisio contains adapted open-source firmware and third-party libraries. The Wisio product naming does not imply that all underlying firmware was originally authored by EchoCore.

## Firmware foundation

The firmware is derived from [Xiaozhi ESP32](https://github.com/78/xiaozhi-esp32). Its MIT license is preserved verbatim in `firmware/LICENSE` and the root `LICENSE`, including:

```text
Copyright (c) 2025 Shenzhen Xinzhi Future Technology Co., Ltd.
Copyright (c) 2025 Project Contributors
```

Existing copyright notices in source and component overrides are retained. Historical source references in technical documentation are attribution, not a connection to the original hosted service. This product uses a local Wisio bridge.

## Identifiers that remain unchanged

- `78/xiaozhi-fonts` / `xiaozhi-fonts`: actual ESP-IDF Component Registry package and build component name. Renaming the reference would not rename the external package and would break dependency resolution.
- ESP-SR model identifiers containing `nihaoxiaozhi`: actual pretrained model names and associated Kconfig symbols. The default Wisio release uses its configured custom wake-word behavior; other supported model choices keep their real identifiers.
- `firmware/main/sdkconfig.rename`: old-to-new symbol mapping used by ESP-IDF to preserve settings from earlier builds.
- Upstream issue, board and model-download links: technical provenance/resources, kept with their correct targets.

## Other dependencies

- ESP-IDF, ESP-SR and Espressif components: see their individual licenses fetched by ESP-IDF Component Manager. `firmware/main/idf_component.yml` and `firmware/dependencies.lock` record dependency identifiers/versions.
- Wi-Fi portal component override: license and notices remain in `firmware/main/overrides/esp-wifi-connect/`.
- Opus: the included `bridge/bin/opus.dll` is accompanied by `bridge/licenses/OPUS-COPYING.txt`.
- Charging-screen font: the supplied license is preserved in `firmware/main/display/charging_font.LICENSE`.
- Python dependencies (websockets, Pillow, imageio-ffmpeg, pyserial, esptool, yt-dlp and their dependencies) are installed by `bridge/setup_bridge.cmd` from `bridge/requirements.txt`. Their own distributions include their licenses; the package does not bundle a developer virtual environment or FFmpeg executable.
- Image/music provider results remain the property of their respective rights holders. Search/stream availability is not a transfer of content ownership.

Git history is not rewritten by this release; earlier commits retain their original attribution and filenames.
