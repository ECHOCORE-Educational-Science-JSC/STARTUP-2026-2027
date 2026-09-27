"""Find a requested song and stream it to the robot as 24 kHz mono PCM."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import os
from pathlib import Path
import subprocess
import sys
import unicodedata


# Keep dependencies beside the bridge so no global Python install is modified.
VENDOR = Path(__file__).with_name("vendor")
if VENDOR.is_dir() and str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    artist: str
    stream_url: str = ""
    webpage_url: str = ""
    http_headers: dict[str, str] = field(default_factory=dict)
    thumbnail_url: str = ""
    duration: float = 0.0


class MusicError(Exception):
    pass


def runtime_problem() -> str | None:
    missing = []
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        missing.append("bộ tìm nhạc")
    try:
        import imageio_ffmpeg
        if not os.path.isfile(imageio_ffmpeg.get_ffmpeg_exe()):
            missing.append("bộ giải mã âm thanh")
    except (ImportError, RuntimeError):
        missing.append("bộ giải mã âm thanh")
    if missing:
        return "Chưa bật được nhạc vì thiếu " + " và ".join(dict.fromkeys(missing)) + "."
    return None


def _words(value: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return set("".join(char if char.isalnum() else " " for char in plain).split())


def _uploader(entry: dict) -> str:
    return str(entry.get("artist") or entry.get("creator") or
               entry.get("uploader") or entry.get("channel") or "").strip()


def search_track(query: str) -> Track:
    """Resolve the best matching YouTube audio result without downloading it."""
    query = query.strip()
    if not query:
        raise MusicError("Bạn chưa nói tên bài hát.")
    problem = runtime_problem()
    if problem:
        raise MusicError(problem)

    from yt_dlp import YoutubeDL
    import re

    clean_query = re.sub(r'^(phát nhạc|bật nhạc|mở nhạc|hát bài|nghe bài|phát bài|bật bài|bài hát|chơi bài|cho tôi nghe bài|cho bé nghe bài|play song|play)\s+', '', query, flags=re.IGNORECASE).strip() or query
    search_query = f"{clean_query} official audio" if clean_query.isascii() and not any(k in clean_query.casefold() for k in ("music", "song", "audio", "lofi", "chill", "remix", "beat", "soundtrack")) else clean_query

    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "format": "bestaudio/best",
        "socket_timeout": 8,
        "retries": 1,
        "extractor_retries": 1,
    }
    try:
        with YoutubeDL(options) as ydl:
            result = ydl.extract_info(f"ytsearch5:{search_query}", download=False)
    except Exception as exc:
        raise MusicError("Không kết nối được nguồn nhạc lúc này.") from exc

    requested = _words(clean_query) or _words(query)
    candidates: list[tuple[float, dict]] = []
    for entry in (result or {}).get("entries") or []:
        if not entry or not entry.get("url"):
            continue
        title = str(entry.get("track") or entry.get("title") or "").strip()
        artist = _uploader(entry)
        title_words = _words(title)
        combined = title_words | _words(artist)
        overlap = len(requested & combined) / max(1, len(requested))
        title_overlap = len(requested & title_words) / max(1, len(requested))
        lowered = title.casefold()
        penalty = 0.35 if any(word in lowered for word in
                              ("reaction", "cover", "karaoke", "remix")) else 0
        candidates.append((overlap + title_overlap * 0.35 - penalty, entry))
    if not candidates:
        raise MusicError(f"Không tìm thấy bài phù hợp với ‘{query}’.")

    score, entry = max(candidates, key=lambda item: item[0])
    if score <= 0.1:
        raise MusicError(f"Không tìm thấy bài phù hợp với ‘{query}’.")
    title = str(entry.get("track") or entry.get("title") or query).strip()
    artist = _uploader(entry) or "YouTube"
    thumbnail_url = str(entry.get("thumbnail") or "").strip()
    duration = float(entry.get("duration") or 0.0)
    return Track(
        str(entry.get("id") or ""), title, artist,
        str(entry.get("url") or ""),
        str(entry.get("webpage_url") or entry.get("original_url") or ""),
        {str(k): str(v) for k, v in (entry.get("http_headers") or {}).items()},
        thumbnail_url=thumbnail_url,
        duration=duration,
    )


def _ffmpeg_executable(explicit: str | None = None) -> str:
    if explicit and os.path.isfile(explicit):
        return explicit
    configured = os.getenv("FFMPEG_PATH", "").strip()
    if configured and os.path.isfile(configured):
        return configured
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise MusicError("Thiếu bộ giải mã âm thanh đi kèm bridge.") from exc


async def pcm_frames(track: Track, frame_bytes: int = 1920,
                     ffmpeg: str | None = None):
    """Decode a resolved stream to 24 kHz mono PCM without saving the song."""
    if not track.stream_url:
        raise MusicError("Nguồn nhạc không cung cấp luồng âm thanh.")
    executable = _ffmpeg_executable(ffmpeg)
    args = [executable, "-hide_banner", "-loglevel", "error",
            "-reconnect", "1", "-reconnect_streamed", "1",
            "-reconnect_delay_max", "1", "-rw_timeout", "5000000"]
    if track.http_headers:
        headers = "".join(f"{key}: {value}\r\n" for key, value in track.http_headers.items())
        args.extend(["-headers", headers])
    args.extend(["-i", track.stream_url, "-vn", "-f", "s16le",
                 "-ac", "1", "-ar", "24000", "pipe:1"])
    # Popen + to_thread works reliably on Windows even when the active asyncio
    # event loop cannot create overlapped subprocess pipes.
    process = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    frames = 0
    try:
        while True:
            frame = await asyncio.to_thread(process.stdout.read, frame_bytes)
            if not frame:
                break
            frames += 1
            yield frame.ljust(frame_bytes, b"\0")
        returncode = await asyncio.to_thread(process.wait)
        if frames == 0 or returncode != 0:
            raise MusicError("Không giải mã được bài hát này.")
    finally:
        if process.poll() is None:
            process.terminate()
        await asyncio.to_thread(process.wait)
