"""Capture USB logs locally without flashing or toggling reset pins."""
from datetime import datetime
from pathlib import Path
import re
import time

import serial
from serial.tools import list_ports


def main():
    ports = [p for p in list_ports.comports() if p.vid == 0x303A]
    if len(ports) != 1:
        print("Khong tim thay dung mot mach ESP32 qua USB.")
        print("Cam cap USB du lieu cua Freenove vao PC va thu lai.")
        return 1
    port = ports[0].device
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.25)
    connection.dtr = False
    connection.rts = False
    connection.port = port
    try:
        connection.open()
    except serial.SerialException:
        print(f"Khong mo duoc {port}. Dong Serial Monitor/phan mem nap dang giu cong nay.")
        return 1
    log_path = Path(__file__).with_name("robot-serial.log")
    try:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"Capture started {datetime.now().isoformat()} port={port}\n")
            log.flush()
            print(f"Da mo {port}. Giu start_bridge dang chay.")
            print("Bam nhanh BOOT hoac cham man hinh mot lan, roi noi mot cau.")
            print("Dang ghi log 45 giay. Khong nap hay xoa firmware.")
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                line = connection.readline().decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if re.search(r"token|authorization|password|api.?key", line, re.I):
                    line = "[credential-containing log line omitted]"
                else:
                    line = re.sub(r"AIza[\w-]+", "[REDACTED]", line)
                print(line, flush=True)
                log.write(line + "\n")
                log.flush()
    except serial.SerialException:
        print("USB da ngat. Phan log da thu van duoc giu lai.")
    finally:
        connection.close()
    print(f"Da luu log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
