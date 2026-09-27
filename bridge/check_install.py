"""Offline checks for a complete Wisio bridge installation."""

from pathlib import Path
import ctypes

import bridge
import imageio_ffmpeg
import websockets
import yt_dlp  # noqa: F401


def main() -> int:
    opus = bridge.find_opus_library()
    ctypes.CDLL(opus)
    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not ffmpeg.is_file():
        raise SystemExit("FFmpeg bundled with imageio-ffmpeg is missing")
    major = int(websockets.__version__.split(".", 1)[0])
    if major != 17:
        raise SystemExit(f"Unsupported websockets version: {websockets.__version__}")
    print("Bridge check: OK")
    print(f"Opus: {opus}")
    print(f"FFmpeg: {ffmpeg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
