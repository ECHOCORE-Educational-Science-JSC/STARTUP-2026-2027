#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wisio Firmware Flasher Tool
Cong cu nap firmware cho Robot Wisio ESP32-S3 (EchoCore Ecosystem)
"""

import os
import sys
import subprocess
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(SCRIPT_DIR, "firmware_bin")

BOOTLOADER_BIN = os.path.join(BIN_DIR, "bootloader.bin")
PARTITION_BIN = os.path.join(BIN_DIR, "partition-table.bin")
OTADATA_BIN = os.path.join(BIN_DIR, "ota_data_initial.bin")
ASSETS_BIN = os.path.join(BIN_DIR, "generated_assets.bin")
APP_BIN = os.path.join(BIN_DIR, "xiaozhi.bin")


def print_banner():
    print("=" * 64)
    print("       ROBOT AI WISIO - CONG CU NAP FIRMWARE TU DONG")
    print("            EchoCore Educational Science JSC")
    print("=" * 64)
    print()


def find_esptool():
    """Tim trinh thuc thi esptool hoac python phu hop"""
    # 1. Thu import ngay trong python hien tai
    try:
        import esptool
        return [sys.executable, "-m", "esptool"]
    except ImportError:
        pass

    # 2. Thu tim trong bridge/.venv
    bridge_venv_py = os.path.join(SCRIPT_DIR, "bridge", ".venv", "Scripts", "python.exe")
    if os.path.isfile(bridge_venv_py):
        res = subprocess.run([bridge_venv_py, "-c", "import esptool"], capture_output=True)
        if res.returncode == 0:
            return [bridge_venv_py, "-m", "esptool"]

    # 3. Thu tim trong C:\Espressif
    espressif_py = r"C:\Espressif\python_env\idf5.5_py3.11_env\Scripts\python.exe"
    espressif_tool = r"C:\Espressif\frameworks\esp-idf-v5.5.3\components\esptool_py\esptool\esptool.py"
    if os.path.isfile(espressif_py) and os.path.isfile(espressif_tool):
        return [espressif_py, espressif_tool]

    # 4. Neu chua co, tu dong cai esptool qua pip
    print("[*] Dang cai dat thu vien esptool va pyserial de nap firmware...")
    res = subprocess.run([sys.executable, "-m", "pip", "install", "esptool", "pyserial"], capture_output=True, text=True)
    if res.returncode == 0:
        return [sys.executable, "-m", "esptool"]

    print("[!] Khong the tu dong cai esptool. Ban hay chay lenh: pip install esptool pyserial")
    return None


def get_available_ports():
    """Liet ke cac cong COM dang ket noi tren may"""
    ports = []
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            desc = p.description or ""
            # Bo qua bluetooth mac dinh neu co the
            is_bt = "bluetooth" in desc.lower()
            ports.append((p.device, desc, is_bt))
    except ImportError:
        # Fallback query PowerShell
        try:
            cmd = ['powershell', '-Command', '[System.IO.Ports.SerialPort]::GetPortNames()']
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                for line in res.stdout.strip().splitlines():
                    p = line.strip()
                    if p:
                        ports.append((p, "Serial Device", False))
        except Exception:
            pass
    return ports


def select_com_port(ports):
    if not ports:
        print("[!] Khong tim thay cong COM nao duoc ket noi!")
        print("    -> Vui long cam cap USB noi bo mach Wisio voi may tinh.")
        print("    -> Dam bao cap USB co truyen data (khong phai cap chi sac).")
        port_input = input("\nNhap cong COM thu cong (vi du COM5): ").strip().upper()
        return port_input if port_input else "COM5"

    print("Cac cong COM dang ket noi:")
    default_idx = 0
    valid_candidates = []
    for i, (port, desc, is_bt) in enumerate(ports):
        marker = " (Bluetooth)" if is_bt else " [Khuyen dung]"
        print(f"  [{i + 1}] {port}: {desc}{marker}")
        if not is_bt and not valid_candidates:
            default_idx = i
        if not is_bt:
            valid_candidates.append(i)

    if len(ports) == 1:
        chosen = ports[0][0]
        print(f"\n-> Tu dong chon cong: {chosen}")
        return chosen

    prompt = f"\nChon cong COM muon nap [1-{len(ports)}] (Mac dinh: [{default_idx + 1}] {ports[default_idx][0]}): "
    choice = input(prompt).strip()
    if not choice:
        return ports[default_idx][0]
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(ports):
            return ports[idx][0]
    except ValueError:
        if choice.upper().startswith("COM"):
            return choice.upper()
    return ports[default_idx][0]


def check_bin_files():
    files = [
        ("Bootloader", BOOTLOADER_BIN),
        ("Partition Table", PARTITION_BIN),
        ("OTA Data", OTADATA_BIN),
        ("Assets (Anh & Am thanh)", ASSETS_BIN),
        ("App (Firmware Wisio)", APP_BIN),
    ]
    missing = []
    for name, path in files:
        if not os.path.isfile(path):
            missing.append(f"{name} ({path})")
    if missing:
        print("[!] Thieu cac file binary sau day:")
        for m in missing:
            print(f"    - {m}")
        return False
    return True


def run_flash(esptool_cmd, port, mode):
    base_args = esptool_cmd + [
        "--chip", "esp32s3",
        "-p", port,
        "-b", "460800",
        "--before", "default_reset",
        "--after", "hard_reset"
    ]

    if mode == "1":
        print(f"\n[*] Dang nap nhanh App firmware ({APP_BIN}) vao {port} tai offset 0x20000...")
        flash_args = base_args + ["write_flash", "0x20000", APP_BIN]
    elif mode == "2":
        print(f"\n[*] Dang nap TOAN BO (Full Flash) vao {port}...")
        flash_args = base_args + [
            "write_flash",
            "--flash_mode", "dio",
            "--flash_freq", "80m",
            "--flash_size", "16MB",
            "0x0", BOOTLOADER_BIN,
            "0x8000", PARTITION_BIN,
            "0xd000", OTADATA_BIN,
            "0x20000", APP_BIN,
            "0x800000", ASSETS_BIN,
        ]
    elif mode == "3":
        print(f"\n[*] Dang xoa sach bo nho Flash tren {port}...")
        flash_args = base_args + ["erase_flash"]
    else:
        print("[!] Lua chon khong hop le.")
        return False

    print(f"Lenh thuc thi: {' '.join(flash_args)}\n")
    start_time = time.time()
    res = subprocess.run(flash_args)
    elapsed = time.time() - start_time

    if res.returncode == 0:
        print("\n" + "=" * 64)
        print(f" [THANH CONG] Da nap xong trong {elapsed:.1f} giay!")
        print(" Robot Wisio se tu khoi dong lai.")
        print("=" * 64)
        return True
    else:
        print("\n" + "=" * 64)
        print(" [THAT BAI] Khong the giao tiep hoac nap vao ESP32-S3!")
        print(" Meo xu ly:")
        print(" 1. Giu nut BOOT tren bo mach, bam nut RESET 1 lan, roi tha nut BOOT.")
        print(" 2. Kiem tra xem co phan mem nao dang giu cong COM (vi du VS Code Serial Monitor).")
        print(" 3. Thu doi sang cong USB khac tren may tinh.")
        print("=" * 64)
        return False


def main():
    print_banner()
    if not check_bin_files():
        input("\nNhan Enter de thoat...")
        sys.exit(1)

    esptool_cmd = find_esptool()
    if not esptool_cmd:
        input("\nNhan Enter de thoat...")
        sys.exit(1)

    ports = get_available_ports()
    selected_port = select_com_port(ports)

    print("\nChon che do nap:")
    print("  [1] Nap cap nhat nhanh (Chi App - ~10 giay) [Khuyen dung, giu nguyen Wi-Fi & Assets]")
    print("  [2] Nap toan bo (Full Flash - ~30 giay) [Danh cho bo moi hoac cai lai tu dau]")
    print("  [3] Xoa sach Flash (Erase Flash) [Xoa trang toan bo de reset]")
    choice = input("\nNhap lua chon [1, 2, 3] (Mac dinh [1]): ").strip()
    if not choice:
        choice = "1"

    run_flash(esptool_cmd, selected_port, choice)
    input("\nNhan Enter de ket thuc...")


if __name__ == "__main__":
    main()
