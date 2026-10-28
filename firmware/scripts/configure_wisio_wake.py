"""Apply Hey Wisio through ESP-IDF Kconfig, preserving current local settings.

Run from the firmware directory in an ESP-IDF terminal after configuring the
Freenove board. This changes configuration only; it never builds or flashes.
"""
import json
import argparse
import os
from pathlib import Path
import shutil

from build import _wake_word_sdkconfig_options


def main():
    import kconfiglib

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', default='build', help='Configured ESP-IDF build directory')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    env_file = root / args.build_dir / "config.env"
    if not env_file.is_file() or not (root / "sdkconfig").is_file():
        raise SystemExit("Configure the Freenove ESP32-S3 project with ESP-IDF first.")
    env = json.loads(env_file.read_text(encoding="utf-8"))
    if env.get("IDF_TARGET") != "esp32s3":
        raise SystemExit("Hey Wisio requires the ESP32-S3 Freenove board.")
    os.environ.update(env)
    os.environ.setdefault("ESP_IDF_VERSION", env["IDF_VERSION"])
    kconf = kconfiglib.Kconfig(str(Path(env["IDF_PATH"]) / "Kconfig"))
    kconf.load_config(str(root / "sdkconfig"))
    board = kconf.syms["BOARD_TYPE_Freenove_ESP32S3_DISPLAY_2_8_LCD"]
    if board.str_value != "y" or kconf.syms["SPIRAM"].str_value != "y":
        raise SystemExit("Select Freenove 2.8-inch ESP32-S3 with PSRAM first.")

    _, options, _ = _wake_word_sdkconfig_options("hey-wisio", "esp32s3")
    desired = {}
    for option in options:
        name, value = option.removeprefix("CONFIG_").split("=", 1)
        if value.startswith('"'):
            value = json.loads(value)
        desired[name] = value
        symbol = kconf.syms.get(name)
        if symbol is None or not symbol.set_value(value):
            raise SystemExit(f"Kconfig rejected {name}={value}")
    for name, value in desired.items():
        if kconf.syms[name].str_value != value:
            raise SystemExit(f"Kconfig dependencies rejected {name}={value}")

    backup = root / "test-tmp/sdkconfig-before-hey-wisio.txt"
    backup.parent.mkdir(exist_ok=True)
    if not backup.exists():
        shutil.copy2(root / "sdkconfig", backup)
    print(kconf.write_config(str(root / "sdkconfig")))
    print("Hey Wisio: English MultiNet5 Q8 with explicit pronunciations, threshold 40%; local settings preserved.")
    print("Build and flash the complete project, including generated_assets.bin.")


if __name__ == "__main__":
    main()
