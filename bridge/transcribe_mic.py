"""Transcribe the diagnostic WAV with Gemini, without the robot bridge."""

import base64
import getpass
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


WAV_PATH = Path(__file__).with_name("diagnostic_mic_loud.wav")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"


def main():
    if not WAV_PATH.is_file():
        raise SystemExit(f"Microphone recording not found: {WAV_PATH}")
    api_key = os.getenv("GEMINI_API_KEY") or getpass.getpass("Paste Gemini API key here (hidden): ")
    api_key = api_key.strip()
    if not api_key:
        raise SystemExit("No API key entered")
    audio = WAV_PATH.read_bytes()
    payload = {"contents": [{"role": "user", "parts": [
        {"text": "Transcribe exactly the speech in this audio. The speaker may use Vietnamese. If there is no intelligible speech, reply only [NO SPEECH]. Do not guess words."},
        {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(audio).decode("ascii")}},
    ]}]}
    request = Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"), headers={
        "Content-Type": "application/json", "x-goog-api-key": api_key,
    })
    try:
        with urlopen(request, timeout=35) as response:
            result = json.load(response)
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace").replace(api_key, "[REDACTED]")
        print(f"Gemini transcription HTTP {exc.code}: {message[:1200]}")
        return
    except URLError as exc:
        print("Network error:", str(exc.reason).replace(api_key, "[REDACTED]"))
        return
    text = " ".join(
        part.get("text", "")
        for candidate in result.get("candidates", [])
        for part in (candidate.get("content") or {}).get("parts", [])
    ).strip()
    print("MIC TRANSCRIPT:", text or "(Gemini returned no text)")


if __name__ == "__main__":
    main()
