"""Re-create the bridge's Opus round trip from the last diagnostic reply."""

import array
import wave
from pathlib import Path

from bridge import (FRAME_MS, OPUS_APPLICATION_AUDIO, OUTPUT_RATE, OUTPUT_SAMPLES,
                    Opus, find_opus_library)


SOURCE = Path(__file__).with_name("diagnostic_reply.wav")
RESULT = Path(__file__).with_name("diagnostic_reply_opus.wav")


def main():
    with wave.open(str(SOURCE), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, OUTPUT_RATE):
            raise SystemExit("Expected Gemini mono 16-bit PCM at 24 kHz")
        original_frames = wav.getnframes()
        pcm = wav.readframes(original_frames)

    codec = Opus(find_opus_library())
    encoder = codec.encoder(OUTPUT_RATE, OPUS_APPLICATION_AUDIO)
    decoder = codec.decoder(OUTPUT_RATE)
    rebuilt = bytearray()
    packet_sizes = []
    try:
        frame_bytes = OUTPUT_SAMPLES * 2
        for offset in range(0, len(pcm), frame_bytes):
            frame = pcm[offset:offset + frame_bytes].ljust(frame_bytes, b"\0")
            packet = codec.encode(encoder, frame)
            packet_sizes.append(len(packet))
            rebuilt.extend(codec.decode(decoder, packet))
    finally:
        codec.lib.opus_encoder_destroy(encoder)
        codec.lib.opus_decoder_destroy(decoder)

    with wave.open(str(RESULT), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(OUTPUT_RATE)
        wav.writeframes(rebuilt[:original_frames * 2])

    samples = array.array("h")
    samples.frombytes(pcm)
    clipped = sum(abs(sample) >= 32760 for sample in samples)
    print(f"Gemini source: {original_frames / OUTPUT_RATE:.2f}s; clipped samples: {clipped}/{len(samples)}")
    print(f"Opus: {len(packet_sizes)} packets of {FRAME_MS}ms; "
          f"average {sum(packet_sizes) / len(packet_sizes):.0f} bytes, "
          f"largest {max(packet_sizes)} bytes")
    print(f"Decoded Opus comparison: {RESULT}")


if __name__ == "__main__":
    main()
