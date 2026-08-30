"""Generates confirm_beep.wav: a short synthesized tone used as the shared
"confirmed/selected" cue (datapack selection, and anywhere else a project in
this repo needs a non-speech confirmation sound -- see README.md in this
directory). Run once; the output is checked in, not regenerated at runtime.

No TTS engine involved on purpose: a pure sine tone is language-independent,
fast to recognize, and trivial to reuse from a completely separate project
(book-scanner) without depending on Piper being available there.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

SAMPLE_RATE = 22050  # matches the rest of this project's datapack audio (Piper's own format)
DURATION_S = 0.2
FREQUENCY_HZ = 880.0  # A5
FADE_S = 0.01  # linear fade in/out, avoids an audible click at the edges
AMPLITUDE = 0.5  # fraction of full int16 scale


def generate_pcm() -> bytes:
    frame_count = int(SAMPLE_RATE * DURATION_S)
    fade_frames = int(SAMPLE_RATE * FADE_S)
    samples = bytearray()
    for i in range(frame_count):
        t = i / SAMPLE_RATE
        envelope = 1.0
        if i < fade_frames:
            envelope = i / fade_frames
        elif i >= frame_count - fade_frames:
            envelope = (frame_count - i) / fade_frames
        value = AMPLITUDE * envelope * math.sin(2 * math.pi * FREQUENCY_HZ * t)
        sample_int16 = int(value * 32767)
        samples += sample_int16.to_bytes(2, byteorder="little", signed=True)
    return bytes(samples)


def main() -> None:
    out_path = Path(__file__).parent / "confirm_beep.wav"
    pcm = generate_pcm()
    with wave.open(str(out_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm)
    print(f"wrote {out_path} ({len(pcm)} bytes PCM, {DURATION_S}s)")


if __name__ == "__main__":
    main()
