"""Google Images via SerpApi; no scraping, SDK, or plaintext saved credentials."""
from __future__ import annotations

from collections import OrderedDict
import ctypes
from ctypes import wintypes
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import threading
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
SECRET_PATH = Path(__file__).with_name('.wisio_serpapi_secret')
_LOCK = threading.Lock()
_SEARCH_CACHE: OrderedDict = OrderedDict()
_KEY_CACHE: dict = {}


class GoogleImageSearchError(Exception):
    """A short diagnostic code, never an upstream URL or credential."""


def _network_failure_reason(error: OSError) -> str:
    # Never stringify urllib exceptions: they can include a URL containing the
    # private API key. Classify only the underlying exception type.
    cause = error.reason if isinstance(error, URLError) else error
    if isinstance(cause, TimeoutError):
        return 'TIMEOUT'
    if isinstance(cause, socket.gaierror):
        return 'DNS_FAILURE'
    if isinstance(cause, ssl.SSLError):
        return 'TLS_FAILURE'
    if isinstance(cause, ConnectionRefusedError):
        return 'CONNECTION_REFUSED'
    return 'NETWORK_ERROR'


def clear_search_cache():
    with _LOCK:
        _SEARCH_CACHE.clear()


def _dpapi(data: bytes, decrypt: bool) -> bytes:
    if os.name != 'nt':
        raise GoogleImageSearchError('SERPAPI_CONFIG: DPAPI chỉ dùng trên Windows; dùng biến SERPAPI_API_KEY.')
    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming, outgoing = Blob(len(data), buf), Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    # UI_FORBIDDEN: loading the bridge must never open a Windows credential dialog.
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise GoogleImageSearchError('SERPAPI_CONFIG: không giải mã được key; chạy CONFIGURE_GOOGLE_IMAGES.cmd lại.')
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        kernel.LocalFree(outgoing.pbData)


def save_api_key(key: str, path: Path = SECRET_PATH):
    key = key.strip()
    if not key or len(key) > 512 or any(ch.isspace() for ch in key):
        raise GoogleImageSearchError('SERPAPI_CONFIG: hãy nhập chính API key, không nhập URL.')
    encrypted = _dpapi(key.encode('utf-8'), False)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_bytes(encrypted)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    with _LOCK:
        _KEY_CACHE.clear()


def get_api_key(path: Path = SECRET_PATH) -> str:
    env = os.getenv('SERPAPI_API_KEY', '').strip()
    if env:
        return env
    try:
        stat = path.stat()
    except FileNotFoundError:
        return ''
    except OSError:
        raise GoogleImageSearchError('SERPAPI_CONFIG: không đọc được file key.') from None
    identity = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    with _LOCK:
        if identity in _KEY_CACHE:
            return _KEY_CACHE[identity]
        try:
            key = _dpapi(path.read_bytes(), True).decode('utf-8').strip()
        except (OSError, UnicodeError):
            raise GoogleImageSearchError('SERPAPI_CONFIG: file key hỏng; cấu hình lại.') from None
        if not key:
            raise GoogleImageSearchError('SERPAPI_KEY_MISSING: cấu hình lại key SerpApi.')
        _KEY_CACHE.clear()
        _KEY_CACHE[identity] = key
        return key


def public_image_url(value) -> bool:
    if not isinstance(value, str) or len(value) > 4096:
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower().rstrip('.')
        if parsed.scheme not in ('http', 'https') or not host or parsed.username or parsed.password:
            return False
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return '.' in host and not any(c.isspace() for c in host)
    except ValueError:
        return False


def _rank(candidate):
    # Google already ranks relevance. Geometry may reorder only four nearby
    # results, never promote an unrelated result from far down the page.
    relevance_group = (candidate['google_position'] - 1) // 4
    try:
        width, height = float(candidate['width']), float(candidate['height'])
        if width <= 0 or height <= 0 or not math.isfinite(width + height):
            return (relevance_group, 2, 9, 0)
        ratio = width / height
        return (relevance_group, 0 if 1 <= ratio <= 2 else 1, abs(math.log(ratio / (4 / 3))), -min(width * height, 1e7))
    except (KeyError, TypeError, ValueError, OverflowError):
        return (relevance_group, 2, 9, 0)


def configured_engine() -> str:
    """Use the lean Google response; retain an explicit classic override."""
    engine = os.getenv('WISIO_GOOGLE_IMAGE_ENGINE', 'google_images_light').strip().lower()
    if engine not in ('google_images_light', 'google_images'):
        # Do not echo arbitrary configuration values: they may contain secrets.
        raise GoogleImageSearchError(
            'SERPAPI_ENGINE_CONFIG: dùng WISIO_GOOGLE_IMAGE_ENGINE=google_images_light hoặc google_images.')
    return engine


def _search_payload(request: Request, deadline: float) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise GoogleImageSearchError('SERPAPI_PROCESSING_TIMEOUT: nguồn ảnh chưa hoàn thành trong thời gian chờ.')
    try:
        with urlopen(request, timeout=min(remaining, 5)) as result:
            raw = result.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GoogleImageSearchError('SERPAPI_RESPONSE_TOO_LARGE')
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get('search_metadata', {}), dict):
            raise ValueError('Invalid envelope')
        if payload.get('error') or payload.get('search_metadata', {}).get('status') == 'Error':
            raise GoogleImageSearchError('SERPAPI_API_ERROR: kiểm tra key và quota trên dashboard SerpApi.')
        return payload
    except HTTPError as exc:
        code = exc.code
        exc.close()
        raise GoogleImageSearchError(f'SERPAPI_HTTP_{code}: kiểm tra key/quota/kết nối SerpApi.') from None
    except OSError as exc:
        reason = _network_failure_reason(exc)
        failure = GoogleImageSearchError(
            f'SERPAPI_TIMEOUT_OR_NETWORK [reason={reason}]: không truy cập được Google Images qua SerpApi.')
        failure.reason = reason
        raise failure from None
    except (ValueError, TypeError):
        raise GoogleImageSearchError('SERPAPI_MALFORMED_RESPONSE') from None


def search_images(query: str, api_key: str, limit: int = 8, timeout: float = 18) -> list[dict]:
    """One search, bounded results, cached candidates; metadata is NEVER proof of identity."""
    engine = configured_engine()
    query = ' '.join(str(query).split())[:1200]
    if not api_key:
        raise GoogleImageSearchError('SERPAPI_KEY_MISSING: chạy CONFIGURE_GOOGLE_IMAGES.cmd.')
    if not query:
        raise GoogleImageSearchError('SERPAPI_QUERY_EMPTY')
    identity = (hashlib.sha256(api_key.encode()).hexdigest(), engine, query)
    with _LOCK:
        cached = _SEARCH_CACHE.get(identity)
        if cached and time.monotonic() - cached[0] < 900:
            _SEARCH_CACHE.move_to_end(identity)
            return [dict(c) for c in cached[1][:limit]]
    parameters = {'engine': engine, 'q': query, 'api_key': api_key,
                  'gl': 'vn', 'hl': 'vi', 'safe': 'active', 'imgar': 'w', 'async': 'true'}
    request = Request('https://serpapi.com/search.json?' + urlencode(parameters),
                      headers={'Accept': 'application/json', 'User-Agent': 'WisioEdu/3.0'})
    budget = float(timeout)
    if not math.isfinite(budget) or budget <= 0:
        raise GoogleImageSearchError('SERPAPI_TIMEOUT_CONFIG')
    deadline = time.monotonic() + min(budget, 30)
    payload = _search_payload(request, deadline)
    job_id = None
    archive_read_retries = 0
    while payload.get('search_metadata', {}).get('status') in ('Queued', 'Processing'):
        metadata = payload['search_metadata']
        identifier = metadata.get('id')
        if (not isinstance(identifier, str) or not re.fullmatch(r'[a-fA-F0-9]{24}', identifier)
                or (job_id is not None and identifier != job_id)):
            raise GoogleImageSearchError('SERPAPI_MALFORMED_RESPONSE')
        job_id = identifier
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GoogleImageSearchError('SERPAPI_PROCESSING_TIMEOUT: nguồn ảnh chưa hoàn thành trong thời gian chờ.')
        # Retrieve the SAME submitted search. Never start another Google search
        # or follow an upstream URL containing credentials to a different host.
        time.sleep(min(.75, remaining))
        archive = Request('https://serpapi.com/searches/' + job_id + '.json?' + urlencode({'api_key': api_key}),
                          headers={'Accept': 'application/json', 'User-Agent': 'WisioEdu/3.0'})
        try:
            payload = _search_payload(archive, deadline)
        except GoogleImageSearchError as exc:
            # A lost archive response does not invalidate the submitted job.
            # Recover once within the same budget; never retry auth/quota errors.
            if (getattr(exc, 'reason', '') != 'TIMEOUT' or archive_read_retries >= 1
                    or time.monotonic() >= deadline):
                raise
            archive_read_retries += 1
    status = payload.get('search_metadata', {}).get('status')
    if (status not in (None, 'Success') or (job_id is not None
            and payload.get('search_metadata', {}).get('id') != job_id)):
        raise GoogleImageSearchError('SERPAPI_MALFORMED_RESPONSE')
    rows = payload.get('images_results', [])
    if not isinstance(rows, list):
        raise GoogleImageSearchError('SERPAPI_MALFORMED_RESPONSE')
    candidates, seen = [], set()
    for position, row in enumerate(rows[:100], 1):
        if not isinstance(row, dict) or row.get('unsafe'):
            continue
        url = row.get('original', '')
        if not public_image_url(url) or url in seen:
            continue
        seen.add(url)
        candidates.append({'url': url, 'title': str(row.get('title') or '')[:300],
                           'google_position': position,
                           'thumbnail': row.get('thumbnail', ''),
                           'page_url': row.get('link', '') if public_image_url(row.get('link')) else '',
                           'width': row.get('original_width'), 'height': row.get('original_height')})
    candidates.sort(key=_rank)
    candidates = candidates[:8]
    with _LOCK:
        _SEARCH_CACHE[identity] = (time.monotonic(), candidates)
        _SEARCH_CACHE.move_to_end(identity)
        while len(_SEARCH_CACHE) > 128:
            _SEARCH_CACHE.popitem(last=False)
    return [dict(c) for c in candidates[:max(0, min(limit, 8))]]


def configuration_status() -> str:
    mode = os.getenv('WISIO_IMAGE_SOURCE', 'auto').strip().lower()
    if mode not in ('auto', 'google', 'legacy'):
        return '[IMAGE CONFIG] INVALID_SOURCE: dùng auto/google/legacy.'
    if mode == 'legacy':
        return '[IMAGE CONFIG] Wikimedia/Openverse (legacy đã được chọn).'
    try:
        engine = configured_engine()
        configured = bool(get_api_key())
    except GoogleImageSearchError as exc:
        return '[IMAGE CONFIG] ' + str(exc)
    if configured:
        return ('[IMAGE CONFIG] Google Images / SerpApi + Gemini pixel verification; '
                f'engine={engine}; cache/prefetch enabled.')
    return ('[IMAGE CONFIG] SERPAPI_KEY_MISSING: Google Images chưa bật. Chạy CONFIGURE_GOOGLE_IMAGES.cmd. '
            + ('Tạm dùng Wikimedia/Openverse.' if mode == 'auto' else 'Không thể tìm ảnh cho đến khi nhập key.'))
