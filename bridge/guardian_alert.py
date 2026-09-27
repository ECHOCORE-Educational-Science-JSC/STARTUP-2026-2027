"""High-confidence guardian alerts for child-safety events."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import smtplib
import ssl
import subprocess
import time
from pathlib import Path
from email.message import EmailMessage


ALERT_PATTERNS = (
    ("tự làm hại bản thân", re.compile(r"\b(tự tử|tự sát|muốn chết|cắt tay|tự làm đau mình)\b", re.I)),
    ("tình dục hoặc nội dung người lớn", re.compile(
        r"\b(làm tình|quan hệ tình dục|phim sex|xem sex|porn|khiêu dâm|gạ tình)\b", re.I)),
    ("đe dọa bạo lực nghiêm trọng", re.compile(
        r"\b(cách (?:giết|đầu độc)|chế (?:bom|súng)|giết người|đâm chết)\b", re.I)),
    ("chất cấm nguy hiểm", re.compile(
        r"\b(cách (?:mua|dùng|chích|điều chế) (?:ma túy|heroin|cocaine|cần sa)|bán ma túy)\b", re.I)),
)


def classify_child_safety(text: str) -> str | None:
    """Return a category only for an explicit, high-confidence safety phrase."""
    normalized = " ".join(str(text).casefold().split())
    if len(normalized) < 4:
        return None
    for category, pattern in ALERT_PATTERNS:
        if pattern.search(normalized):
            return category
    return None


class GuardianAlerter:
    COOLDOWN_SECONDS = 30 * 60

    def __init__(self, recipient: str):
        self.recipient = recipient.strip()
        self.sender = os.getenv("WISIO_ALERT_GMAIL", "").strip() or _saved_sender()
        self.password = (os.getenv("WISIO_ALERT_APP_PASSWORD", "").strip() or
                         _decrypt_saved_password()).replace(" ", "")
        self._last_sent_at = 0.0
        self._last_fingerprint = ""

    @property
    def ready(self) -> bool:
        return bool(self.recipient and "@" in self.recipient and self.sender and self.password)

    async def notify(self, category: str, transcript: str) -> bool:
        if not self.ready:
            return False
        fingerprint = hashlib.sha256(f"{category}\0{transcript.casefold()}".encode("utf-8")).hexdigest()
        now = time.monotonic()
        if fingerprint == self._last_fingerprint or now - self._last_sent_at < self.COOLDOWN_SECONDS:
            return False
        sent = await asyncio.to_thread(self._send, category, transcript)
        if sent:
            self._last_fingerprint = fingerprint
            self._last_sent_at = now
        return sent

    def _send(self, category: str, transcript: str) -> bool:
        message = EmailMessage()
        message["From"] = f"Wisio Safety <{self.sender}>"
        message["To"] = self.recipient
        message["Subject"] = "Wisio: cảnh báo nội dung cần phụ huynh lưu ý"
        message.set_content(
            "Wisio phát hiện một câu nói cần phụ huynh xem xét.\n\n"
            f"Nhóm nội dung: {category}\n"
            f"Câu Wisio nghe được: {transcript[:500]}\n\n"
            "Đây là cảnh báo tự động theo ngưỡng thận trọng cao. "
            "Hãy trò chuyện bình tĩnh với bé và xem xét bối cảnh trước khi kết luận."
        )
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=15) as smtp:
                smtp.login(self.sender, self.password)
                smtp.send_message(message)
            return True
        except (OSError, smtplib.SMTPException):
            return False


def _saved_sender() -> str:
    path = Path(__file__).with_name(".wisio_alert_sender")
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _decrypt_saved_password() -> str:
    """Read a per-Windows-user DPAPI secret created by the setup helper."""
    path = Path(__file__).with_name(".wisio_alert_secret")
    if os.name != "nt" or not path.is_file():
        return ""
    quoted = str(path).replace("'", "''")
    script = (
        f"$e=Get-Content -LiteralPath '{quoted}' -Raw;"
        "$s=ConvertTo-SecureString $e;"
        "$p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);"
        "try{[Runtime.InteropServices.Marshal]::PtrToStringBSTR($p)}"
        "finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True, capture_output=True, text=True, timeout=8,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
