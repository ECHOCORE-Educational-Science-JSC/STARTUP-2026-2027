"""Find a requested song and stream it to the robot as 24 kHz mono PCM."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import os
from pathlib import Path
import subprocess
import sys
import unicodedata
import json
import re
import shutil
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
    provider: str = "audius"


class MusicError(Exception):
    pass


AUDIUS_API = "https://api.audius.co/v1"


def runtime_problem() -> str | None:
    missing = []
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


def _match_score(title: str, artist: str, requested: set[str]) -> float:
    title_words = _words(title)
    combined = title_words | _words(artist)
    overlap = len(requested & combined) / max(1, len(requested))
    title_overlap = len(requested & title_words) / max(1, len(requested))
    lowered = title.casefold()
    penalty = 0.35 if any(word in lowered for word in
                          ("reaction", "cover", "karaoke", "remix")) else 0
    return overlap + title_overlap * 0.35 - penalty


def _is_relevant_match(title: str, artist: str, requested: set[str],
                       generic_request: bool) -> bool:
    if generic_request:
        return True
    selected_words = _words(title) | _words(artist)
    coverage = len(requested & selected_words) / max(1, len(requested))
    return coverage >= 0.75


def _search_audius_track(query: str, requested: set[str],
                         generic_request: bool,
                         excluded_ids: set[str] | None = None) -> Track | None:
    """Search Audius' public catalog for a playable matching track."""
    params = urlencode({"query": query, "limit": 10})
    request = Request(
        f"{AUDIUS_API}/tracks/search?{params}",
        headers={"Accept": "application/json", "User-Agent": "Wisio-EchoCore/1.0"},
    )
    try:
        with urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
        raise MusicError("Không kết nối được nguồn nhạc Audius lúc này. Bé thử lại sau nhé.") from None

    candidates: list[tuple[float, dict]] = []
    excluded_ids = excluded_ids or set()
    for entry in (payload or {}).get("data") or []:
        if (not entry or entry.get("is_stream_gated") or
                str(entry.get("id") or "") in excluded_ids):
            continue
        title = str(entry.get("title") or "").strip()
        user = entry.get("user") or {}
        artist = str(user.get("name") or user.get("handle") or "").strip()
        track_id = str(entry.get("id") or "").strip()
        if not title or not track_id:
            continue
        duration = float(entry.get("duration") or 0.0)
        playable_bonus = 0.15 if duration == 0 or duration >= 45 else -0.4
        candidates.append((_match_score(title, artist, requested) + playable_bonus, entry))
    if not candidates:
        return None

    score, entry = max(candidates, key=lambda item: item[0])
    user = entry.get("user") or {}
    artist = str(user.get("name") or user.get("handle") or "Audius").strip()
    title = str(entry.get("title") or query).strip()
    if (not generic_request and score <= 0.1) or not _is_relevant_match(
            title, artist, requested, generic_request):
        return None
    track_id = str(entry.get("id"))
    artwork = entry.get("artwork") or {}
    thumbnail_url = str(
        artwork.get("480x480") or artwork.get("1000x1000") or
        artwork.get("150x150") or ""
    ).strip()
    permalink = str(entry.get("permalink") or "").strip()
    if permalink.startswith("/"):
        permalink = "https://audius.co" + permalink
    clean_artist = clean_artist_name(artist) or "Audius"
    clean_title = clean_track_title(title, clean_artist) or title
    return Track(
        track_id,
        clean_title,
        clean_artist,
        f"{AUDIUS_API}/tracks/{track_id}/stream",
        permalink,
        thumbnail_url=thumbnail_url,
        duration=float(entry.get("duration") or 0.0),
        display_title=clean_title,
        display_artist=clean_artist,
        provider="audius",
    )


class _ExtractorLog:
    # yt-dlp otherwise prints raw extractor URLs and errors to the voice console.
    def debug(self, message): pass
    def warning(self, message): pass
    def error(self, message): pass


def _youtube_options(flat: bool = False) -> dict:
    runtimes = {}
    for name in ("deno", "node"):
        executable = shutil.which(name)
        if executable:
            runtimes[name] = {"path": executable}
    return {
        "quiet": True, "no_warnings": True, "logger": _ExtractorLog(),
        "skip_download": True, "noplaylist": True,
        "extract_flat": flat, "format": "bestaudio/best",
        "socket_timeout": 4, "retries": 0, "extractor_retries": 0,
        "js_runtimes": runtimes,
        "cachedir": str(Path(__file__).with_name(".cache") / "youtube"),
    }


def _youtube_track(info: dict) -> Track | None:
    video_id = str(info.get("id") or "")
    stream = str(info.get("url") or "")
    if (not re.fullmatch(r"[\w-]{11}", video_id, flags=re.ASCII) or
            not stream.startswith(("https://", "http://")) or
            info.get("is_live") or (info.get("age_limit") or 0) >= 18 or
            info.get("has_drm")):
        return None
    artist = clean_artist_name(_uploader(info))
    title = clean_track_title(str(info.get("title") or ""), artist)
    if not title:
        return None
    return Track(
        video_id, title, artist, stream,
        f"https://www.youtube.com/watch?v={video_id}",
        http_headers=dict(info.get("http_headers") or {}),
        thumbnail_url=str(info.get("thumbnail") or ""),
        duration=float(info.get("duration") or 0),
        display_title=title, display_artist=artist, provider="youtube")


def _search_youtube_track(query: str, requested: set[str], generic_request: bool,
                          excluded_ids: set[str]) -> Track | None:
    try:
        import yt_dlp
    except ImportError:
        raise MusicError("Thiếu thành phần YouTube. Chạy setup_bridge.cmd để cài lại.") from None
    try:
        with yt_dlp.YoutubeDL(_youtube_options(flat=True)) as extractor:
            results = extractor.extract_info(f"ytsearch8:{query}", download=False) or {}
    except Exception:
        raise MusicError("Không kết nối được nguồn nhạc YouTube lúc này.") from None
    candidates = []
    for entry in results.get("entries") or []:
        if not entry:
            continue
        video_id = str(entry.get("id") or "")
        title, artist = str(entry.get("title") or ""), _uploader(entry)
        if (not re.fullmatch(r"[\w-]{11}", video_id, flags=re.ASCII) or
                video_id in excluded_ids or entry.get("is_live") or
                (entry.get("age_limit") or 0) >= 18 or
                entry.get("availability") in ("private", "premium_only", "subscriber_only") or
                not _is_relevant_match(title, artist, requested, generic_request)):
            continue
        candidates.append((_match_score(title, artist, requested), video_id))
    # Resolve only the best few matching videos, skipping a removed/unplayable one.
    for _, video_id in sorted(candidates, reverse=True, key=lambda item: item[0])[:3]:
        try:
            with yt_dlp.YoutubeDL(_youtube_options()) as extractor:
                info = extractor.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False) or {}
            track = _youtube_track(info)
            if track and _is_relevant_match(track.title, track.artist, requested, generic_request):
                return track
        except Exception:
            continue
    if candidates:
        raise MusicError("Các video YouTube phù hợp hiện không cung cấp âm thanh phát được.")
    return None


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
    """Extract canonical song name by removing noisy publication and clickbait tags."""
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



def search_track(query: str, excluded_ids: set[str] | None = None) -> Track:
    """Prefer Audius and fall back to matching YouTube audio, without saving songs."""
    import re

    query = query.strip()
    if not query:
        raise MusicError("Bạn chưa nói tên bài hát.")
    problem = runtime_problem()
    if problem:
        raise MusicError(problem)
    clean_query = re.sub(
        r'^(phát nhạc|bật nhạc|mở nhạc|hát bài|nghe bài|phát bài|bật bài|bài hát|chơi bài|cho tôi nghe bài|cho bé nghe bài|play song|play)\s*',
        '', query, flags=re.IGNORECASE).strip()
    filler = {"cho", "toi", "be", "minh", "nghe", "voi", "nhe", "di", "mot", "bai", "nhac", "phat", "bat", "mo"}
    request_words = _words(clean_query or query)
    generic_request = not (request_words - filler)
    if generic_request:
        clean_query = "happy instrumental"
    requested = (request_words - filler) or request_words
    excluded = set(excluded_ids or ())
    errors = []
    for finder in (_search_audius_track, _search_youtube_track):
        try:
            track = finder(clean_query or query, requested, generic_request, excluded)
            if track is not None:
                return track
        except MusicError as exc:
            errors.append(str(exc))
    if errors:
        raise MusicError("Chưa mở được nhạc. " + " ".join(errors))
    raise MusicError(
        f"Audius và YouTube chưa có bài phù hợp với ‘{query}’ để phát. Bé thử tên bài hoặc ca sĩ khác nhé.")


def refresh_track_stream(track: Track) -> Track:
    """Renew expiring YouTube URLs; Audius uses a stable public endpoint."""
    if track.provider == "audius":
        return track
    if track.provider != "youtube" or not re.fullmatch(r"[\w-]{11}", track.id, flags=re.ASCII):
        raise MusicError("Nguồn nhạc không hợp lệ. Hãy tìm lại bài hát.")
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL(_youtube_options()) as extractor:
            info = extractor.extract_info(
                f"https://www.youtube.com/watch?v={track.id}", download=False) or {}
        fresh = _youtube_track(info)
        if fresh is not None and fresh.id == track.id:
            return fresh
    except Exception:
        pass
    raise MusicError("Chưa làm mới được luồng âm thanh YouTube. Hãy tìm lại bài hát.")


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
