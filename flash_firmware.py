"""Flash the matching wake app and model together; never erase NVS/Wi-Fi."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
FILES = [(0, 'bootloader.bin'), (0x8000, 'partition-table.bin'),
         (0xd000, 'ota_data_initial.bin'), (0x20000, 'wisio.bin'),
         (0x800000, 'generated_assets.bin')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    for line in (ROOT / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        expected, name = line.split('  ', 1)
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise SystemExit('Invalid package path')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit(f'Checksum mismatch: {name}')
    print('Package checksums OK; app and MultiNet5 Q8 model are paired.')
    if args.check_only:
        return
    port = args.port or input('Cong COM cua robot (vi du COM8): ').strip()
    if not port:
        raise SystemExit('Chua chon cong COM.')
    command = [sys.executable, '-m', 'esptool', '--chip', 'esp32s3', '--port', port,
               '-b', '460800', '--before', 'default_reset', '--after', 'hard_reset',
               'write_flash', '--flash_mode', 'dio', '--flash_freq', '80m', '--flash_size', '16MB']
    for offset, name in FILES:
        command.extend([hex(offset), str(ROOT / 'firmware_bin' / name)])
    raise SystemExit(subprocess.run(command).returncode)


if __name__ == '__main__':
    main()
