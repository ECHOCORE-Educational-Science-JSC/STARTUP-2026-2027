"""Replay a Freenove mic recording into Gemini Live without the robot bridge."""

import asyncio
import base64
import getpass
import json
import os
import wave
from pathlib import Path
from urllib.parse import quote

import websockets

from bridge import GEMINI_ENDPOINT, GEMINI_MODEL, audio_generation_config, boost_pcm, new_speech_state, send_json


WAV_PATH = Path(__file__).with_name("diagnostic_mic.wav")


def frames_from_wav(path: Path):
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
            raise ValueError("Expected mono, 16-bit, 16 kHz WAV")
        frames = []
        while chunk := wav.readframes(960):
            frames.append(chunk)
    return frames


async def trial(api_key: str, frames: list[bytes], manual: bool):
    label = "MANUAL VAD" if manual else "AUTOMATIC VAD"
    print(f"\n{label}: connecting to {GEMINI_MODEL}")
    url = GEMINI_ENDPOINT + "?key=" + quote(api_key, safe="")
    audio_chunks = 0
    input_text = []
    output_text = []
    try:
        async with websockets.connect(url, max_size=16 * 1024 * 1024, open_timeout=10) as gemini:
            detection = {"disabled": True} if manual else {
                "startOfSpeechSensitivity": "START_SENSITIVITY_HIGH",
                "silenceDurationMs": 700,
            }
            await send_json(gemini, {"setup": {
                "model": f"models/{GEMINI_MODEL}",
                "generationConfig": audio_generation_config(),
                "inputAudioTranscription": {},
                "outputAudioTranscription": {},
                "realtimeInputConfig": {"automaticActivityDetection": detection},
                "systemInstruction": {"parts": [{"text": (
                    "You are a helpful voice assistant. Always answer a direct spoken question aloud in one short sentence."
                )}]},
            }})
            setup = json.loads(await asyncio.wait_for(gemini.recv(), 10))
            if "setupComplete" not in setup:
                print(label, "setup error:", setup)
                return False
            if manual:
                await send_json(gemini, {"realtimeInput": {"activityStart": {}}})
            mic_state = new_speech_state()
            for frame in frames:
                await send_json(gemini, {"realtimeInput": {"audio": {
                    "data": base64.b64encode(boost_pcm(frame, mic_state)).decode("ascii"),
                    "mimeType": "audio/pcm;rate=16000",
                }}})
                await asyncio.sleep(len(frame) / (16000 * 2))
            await send_json(gemini, {"realtimeInput": (
                {"activityEnd": {}} if manual else {"audioStreamEnd": True}
            )})
            print(label, f"sent {len(frames)} audio frames; waiting up to 15 seconds")
            async with asyncio.timeout(15):
                async for raw in gemini:
                    event = json.loads(raw)
                    if "error" in event:
                        print(label, "Gemini error:", event["error"])
                        break
                    content = event.get("serverContent") or {}
                    if content:
                        print(label, "event:", ", ".join(content.keys()))
                    if (content.get("inputTranscription") or {}).get("text"):
                        input_text.append(content["inputTranscription"]["text"])
                    if (content.get("outputTranscription") or {}).get("text"):
                        output_text.append(content["outputTranscription"]["text"])
                    for part in (content.get("modelTurn") or {}).get("parts", []):
                        if (part.get("inlineData") or {}).get("data"):
                            audio_chunks += 1
                    if content.get("turnComplete"):
                        break
    except TimeoutError:
        print(label, "timed out without a complete turn")
    except Exception as exc:
        print(label, "connection error:", type(exc).__name__, str(exc).replace(api_key, "[REDACTED]"))
    print(label, "result:", audio_chunks, "audio chunks; heard:", "".join(input_text) or "(none)",
          "; replied:", "".join(output_text) or "(none)")
    return audio_chunks > 0


async def main():
    if not WAV_PATH.is_file():
        raise SystemExit(f"Microphone recording missing: {WAV_PATH}")
    frames = frames_from_wav(WAV_PATH)
    print(f"Recorded Freenove audio: {len(frames)} frames, about {len(frames) * 0.06:.1f}s")
    api_key = os.getenv("GEMINI_API_KEY") or getpass.getpass("Paste Gemini API key here (hidden): ")
    api_key = api_key.strip()
    if not api_key:
        raise SystemExit("No API key entered")
    if not await trial(api_key, frames, manual=True):
        await asyncio.sleep(1)
        await trial(api_key, frames, manual=False)


if __name__ == "__main__":
    asyncio.run(main())
