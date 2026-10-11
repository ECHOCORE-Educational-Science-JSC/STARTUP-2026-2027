"""Verify the distributed files without touching serial ports or the network."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent


def verify(root=ROOT):
    root = Path(root).resolve()
    sums = root / 'SHA256SUMS.txt'
    for line in sums.read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f'Unsafe package path: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Checksum mismatch: {name}')
    manifest = json.loads((root / 'firmware_bin/manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        path = (root / 'firmware_bin' / item['file']).resolve()
        if not path.is_relative_to(root / 'firmware_bin'):
            raise ValueError('Unsafe firmware path')
        if path.stat().st_size != item['bytes']:
            raise ValueError(f"Wrong binary size: {item['file']}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError(f"Wrong binary hash: {item['file']}")
    print(f'Wisio package checksums: OK ({len(sums.read_text().splitlines())} files)')


if __name__ == '__main__':
    verify()
