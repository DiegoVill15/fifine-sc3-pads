"""Write a WAV file of every style and pad, to listen to them outside the app.

Usage: python tools/make_samples.py   (creates samples/)
"""
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from audio import PAD_TONES, STYLES, make_signature  # noqa: E402

RATE = 48000


def main():
    out = ROOT / "samples"
    out.mkdir(exist_ok=True)
    for style in STYLES:
        for pad in PAD_TONES:
            sig = make_signature(pad, RATE, style, level=0.5)
            with wave.open(str(out / f"{style}-{pad}.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes((sig * 32767).astype("<i2").tobytes())
    print(f"Samples written to {out}")


if __name__ == "__main__":
    main()
