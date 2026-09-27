"""Check whether Gemini Live can produce audio without Freenove or its microphone."""

import asyncio
import getpass
import json
import os
from urllib.parse import quote

import websockets

from bridge import GEMINI_ENDPOINT, GEMINI_MODEL, audio_generation_config, send_json


async def main():
    api_key = os.getenv("GEMINI_API_KEY") or getpass.getpass("Paste Gemini API key here (hidden): ")
    api_key = api_key.strip()
    if not api_key:
        raise SystemExit("No API key entered")
    url = GEMINI_ENDPOINT + "?key=" + quote(api_key, safe="")
    audio_chunks = 0
    transcript = []
    try:
        async with websockets.connect(url, max_size=16 * 1024 * 1024, open_timeout=10) as gemini:
            await send_json(gemini, {"setup": {
                "model": f"models/{GEMINI_MODEL}",
                "generationConfig": audio_generation_config(),
                "outputAudioTranscription": {},
                "systemInstruction": {"parts": [{"text": "Always reply aloud, even to a short greeting. Be brief."}]},
            }})
            setup = json.loads(await asyncio.wait_for(gemini.recv(), 10))
            if "setupComplete" not in setup:
                print("Gemini setup result:", json.dumps(setup, ensure_ascii=False))
                return
            print("Gemini Live connected; sending a text greeting without the robot.")
            await send_json(gemini, {"clientContent": {
                "turns": [{"role": "user", "parts": [{"text": "Say hello in one short sentence."}]}],
                "turnComplete": True,
            }})
            async with asyncio.timeout(20):
                async for raw in gemini:
                    event = json.loads(raw)
                    if "error" in event:
                        print("Gemini error:", event["error"])
                        break
                    content = event.get("serverContent") or {}
                    if content:
                        print("Gemini event:", ", ".join(content.keys()))
                    spoken_text = (content.get("outputTranscription") or {}).get("text")
                    if spoken_text:
                        transcript.append(spoken_text)
                    for part in (content.get("modelTurn") or {}).get("parts", []):
                        if (part.get("inlineData") or {}).get("data"):
                            audio_chunks += 1
                    if content.get("turnComplete"):
                        break
    except TimeoutError:
        print("Timed out after 20 seconds without a complete response.")
    except Exception as exc:
        print("Gemini connection error:", type(exc).__name__, str(exc).replace(api_key, "[REDACTED]"))
    print(f"Result: {audio_chunks} audio chunks; transcript: {''.join(transcript) or '(none)'}")
    if audio_chunks:
        print("Gemini can speak. The remaining problem is in microphone audio or the robot bridge.")
    else:
        print("Gemini did not produce speech even without the robot. Check the API/session error above.")


if __name__ == "__main__":
    asyncio.run(main())
