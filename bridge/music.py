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
    display_title: str = ""
    display_artist: str = ""


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


VN_FONT_FALLBACK = {
    'Ă': 'A',  # U+0102
    'Đ': 'D',  # U+0110
    'Ĩ': 'I',  # U+0128
    'ĩ': 'i',  # U+0129
    'Ũ': 'U',  # U+0168
    'ũ': 'u',  # U+0169
    'Ơ': 'O',  # U+01A0
    'ơ': 'o',  # U+01A1
    'Ư': 'U',  # U+01AF
    'ư': 'u',  # U+01B0
    'Ạ': 'A',  # U+1EA0
    'Ả': 'A',  # U+1EA2
    'Ấ': 'A',  # U+1EA4
    'Ầ': 'A',  # U+1EA6
    'Ẩ': 'A',  # U+1EA8
    'ẩ': 'a',  # U+1EA9
    'Ẫ': 'A',  # U+1EAA
    'ẫ': 'a',  # U+1EAB
    'Ậ': 'A',  # U+1EAC
    'Ắ': 'A',  # U+1EAE
    'Ằ': 'A',  # U+1EB0
    'ằ': 'a',  # U+1EB1
    'Ẳ': 'A',  # U+1EB2
    'ẳ': 'a',  # U+1EB3
    'Ẵ': 'A',  # U+1EB4
    'ẵ': 'a',  # U+1EB5
    'Ặ': 'A',  # U+1EB6
    'ặ': 'a',  # U+1EB7
    'Ẹ': 'E',  # U+1EB8
    'ẹ': 'e',  # U+1EB9
    'Ẻ': 'E',  # U+1EBA
    'Ẽ': 'E',  # U+1EBC
    'Ế': 'E',  # U+1EBE
    'Ề': 'E',  # U+1EC0
    'ề': 'e',  # U+1EC1
    'Ể': 'E',  # U+1EC2
    'Ễ': 'E',  # U+1EC4
    'ễ': 'e',  # U+1EC5
    'Ệ': 'E',  # U+1EC6
    'Ỉ': 'I',  # U+1EC8
    'ỉ': 'i',  # U+1EC9
    'Ị': 'I',  # U+1ECA
    'Ọ': 'O',  # U+1ECC
    'ọ': 'o',  # U+1ECD
    'Ỏ': 'O',  # U+1ECE
    'ỏ': 'o',  # U+1ECF
    'Ố': 'O',  # U+1ED0
    'Ồ': 'O',  # U+1ED2
    'Ổ': 'O',  # U+1ED4
    'ổ': 'o',  # U+1ED5
    'Ỗ': 'O',  # U+1ED6
    'Ộ': 'O',  # U+1ED8
    'Ớ': 'O',  # U+1EDA
    'Ờ': 'O',  # U+1EDC
    'Ở': 'O',  # U+1EDE
    'Ỡ': 'O',  # U+1EE0
    'ỡ': 'o',  # U+1EE1
    'Ợ': 'O',  # U+1EE2
    'Ụ': 'U',  # U+1EE4
    'Ủ': 'U',  # U+1EE6
    'Ứ': 'U',  # U+1EE8
    'ứ': 'u',  # U+1EE9
    'Ừ': 'U',  # U+1EEA
    'ừ': 'u',  # U+1EEB
    'Ử': 'U',  # U+1EEC
    'Ữ': 'U',  # U+1EEE
    'ữ': 'u',  # U+1EEF
    'Ự': 'U',  # U+1EF0
    'ự': 'u',  # U+1EF1
    'Ỳ': 'Y',  # U+1EF2
    'ỳ': 'y',  # U+1EF3
    'Ỵ': 'Y',  # U+1EF4
    'ỵ': 'y',  # U+1EF5
    'Ỷ': 'Y',  # U+1EF6
    'ỷ': 'y',  # U+1EF7
    'Ỹ': 'Y',  # U+1EF8
    'ỹ': 'y',  # U+1EF9
}


def make_font_safe(text: str) -> str:
    """Map Vietnamese characters missing in LCD basic font to safe base letters."""
    return ''.join(VN_FONT_FALLBACK.get(c, c) for c in text)


def clean_artist_name(raw_artist: str) -> str:
    """Clean channel and management noise from artist names."""
    artist = str(raw_artist or "").strip()
    if not artist:
        return ""
    import re
    artist = re.sub(
        r"\s*(?:official\s*(?:channel|music|vevo)?|channel|\-\s*topic|vevo|entertainment|records)\s*$",
        "",
        artist,
        flags=re.IGNORECASE,
    ).strip()
    return artist or str(raw_artist or "").strip()


def clean_track_title(raw_title: str, artist: str = "") -> str:
    """Extract canonical song name by removing YouTube noise and clickbait tags."""
    title = str(raw_title or "").strip()
    if not title:
        return ""

    import re

    # Remove square brackets, parentheses, curly braces containing noisy tags
    tag_pattern = (
        r"[\(\[\{]\s*(?:"
        r"official\s*(?:music\s*)?video|"
        r"official\s*mv|"
        r"official\s*audio|"
        r"audio\s*official|"
        r"official|"
        r"mv\s*4k|"
        r"mv|"
        r"4k|"
        r"hd|"
        r"full\s*hd|"
        r"audio|"
        r"lyrics?|"
        r"lyric\s*video|"
        r"lyrics\s*video|"
        r"visualizer|"
        r"nhạc\s*thiếu\s*nhi[^)\]}]*|"
        r"bản\s*chuẩn|"
        r"video\s*clip|"
        r"performance\s*video|"
        r"karaoke|"
        r"beat|"
        r"teaser|"
        r"trailer|"
        r"chính\s*thức"
        r")\s*[\)\]\}]"
    )
    title = re.sub(tag_pattern, "", title, flags=re.IGNORECASE)

    # Remove pipe segments that are junk
    junk_re = re.compile(
        r"^(?:"
        r"official\s*(?:music\s*)?video|"
        r"official\s*mv|"
        r"official\s*audio|"
        r"official|"
        r"mv\s*4k|"
        r"mv|"
        r"audio|"
        r"lyrics?|"
        r"visualizer|"
        r"nhạc\s*thiếu\s*nhi.*|"
        r"nhạc\s*sống.*|"
        r"nhạc\s*trẻ.*|"
        r"hot\s*tiktok.*|"
        r"tik\s*tok.*"
        r")$",
        re.IGNORECASE,
    )
    clean_art = clean_artist_name(artist) if artist else ""
    if "|" in title:
        parts = [p.strip() for p in title.split("|") if p.strip()]
        valid_parts = [p for p in parts if not junk_re.match(p)]
        if len(valid_parts) == 1:
            title = valid_parts[0]
        elif len(valid_parts) >= 2:
            if clean_art:
                p0, p1 = valid_parts[0], valid_parts[1]
                if clean_art.casefold() in p0.casefold() or p0.casefold() in clean_art.casefold():
                    title = p1
                elif clean_art.casefold() in p1.casefold() or p1.casefold() in clean_art.casefold():
                    title = p0
                else:
                    title = p0
            else:
                title = " - ".join(valid_parts[:2])

    # Remove trailing hyphen tags e.g. "- Official MV" or "- Nhạc Thiếu Nhi Sôi Động..."
    title = re.sub(
        r"\s*-\s*(?:official\s*(?:music\s*)?video|official\s*mv|official\s*audio|official|mv\s*4k|mv|audio|lyric(?:s)?(?:\s*video)?|visualizer|nhạc\s*(?:thiếu\s*nhi|trẻ|sống|chế|vàng|trữ\s*tình|sôi\s*động).*|top\s*hit.*|hot\s*tiktok.*)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    if clean_art and " - " in title:
        parts = [p.strip() for p in title.split(" - ") if p.strip()]
        if len(parts) == 2:
            p0, p1 = parts[0], parts[1]
            if clean_art.casefold() in p0.casefold() or p0.casefold() in clean_art.casefold():
                title = p1
            elif clean_art.casefold() in p1.casefold() or p1.casefold() in clean_art.casefold():
                title = p0

    if title.isupper() and len(title) > 3:
        title = title.title()
        for acr in ("M-Tp", "M-tp", "Mv", "Edm", "Dj", "Mc", "Remix", "Vip"):
            title = re.sub(r'\b' + re.escape(acr) + r'\b', acr.upper() if acr.lower() != "m-tp" else "M-TP", title)

    # Clean whitespace and boundary punctuation
    title = title.strip(' "\' -:')
    title = re.sub(r"\s+", " ", title).strip()
    return title or str(raw_title).strip()



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
        raise MusicError(f"Không tìm thấy bài phù hợp với ‘{query}’. Bé thử tìm bài khác xem sao nhé!")

    score, entry = max(candidates, key=lambda item: item[0])
    if score <= 0.1:
        raise MusicError(f"Không tìm thấy bài phù hợp với ‘{query}’. Bé thử tìm bài khác xem sao nhé!")
    raw_track = str(entry.get("track") or "").strip()
    raw_title = str(entry.get("title") or query).strip()
    clean_art = clean_artist_name(_uploader(entry)) or "YouTube"
    if raw_track:
        title = clean_track_title(raw_track, clean_art) or raw_track
    else:
        title = clean_track_title(raw_title, clean_art) or raw_title
    thumbnail_url = str(entry.get("thumbnail") or "").strip()
    duration = float(entry.get("duration") or 0.0)
    return Track(
        str(entry.get("id") or ""),
        title,
        clean_art,
        str(entry.get("url") or ""),
        str(entry.get("webpage_url") or entry.get("original_url") or ""),
        {str(k): str(v) for k, v in (entry.get("http_headers") or {}).items()},
        thumbnail_url=thumbnail_url,
        duration=duration,
        display_title=make_font_safe(title),
        display_artist=make_font_safe(clean_art),
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
