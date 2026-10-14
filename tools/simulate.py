"""Simulate loud music plus pad signatures to measure hits and false triggers.

Usage: python tools/simulate.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import detector as det  # noqa: E402
from audio import PAD_TONES, STYLES, make_signature  # noqa: E402

RATE = 48000
BLOCK = int(RATE * det.BLOCK_S)
rng = np.random.default_rng(7)


def music(seconds, dbfs):
    """Random chords with harmonics changing every 250 ms, plus pink noise."""
    n = int(RATE * seconds)
    t = np.arange(n) / RATE
    x = np.zeros(n)
    step = int(RATE * 0.25)
    for i in range(0, n, step):
        seg = slice(i, min(i + step, n))
        for midi in rng.integers(40, 84, 4):
            f0 = 440 * 2 ** ((midi - 69) / 12)
            for h in range(1, 6):
                x[seg] += np.sin(2 * np.pi * f0 * h * t[seg] + rng.uniform(0, 6)) / h
    spec = np.fft.rfft(rng.normal(0, 1, n))
    spec[1:] /= np.sqrt(np.arange(1, len(spec)))
    pink = np.fft.irfft(spec, n)
    x += 3 * pink / pink.std()
    return x / np.sqrt((x ** 2).mean()) * 10 ** (dbfs / 20)


def detect(x):
    d = det.Detector(RATE)
    return [p for i in range(len(x) // BLOCK) if (p := d.feed(x[i * BLOCK:(i + 1) * BLOCK].astype("float32")))]


def main():
    print("False triggers in 5 min of loud music (-20 dBFS):", len(detect(music(300, -20))))
    for style in STYLES:
        results = []
        for pad in PAD_TONES:
            hits = wrong = 0
            for _ in range(10):
                sig = make_signature(pad, RATE, style, level=10 ** (-25 / 20))
                sig = sig[int(RATE * rng.uniform(0, 0.2)):]   # the pad trims the start
                x = np.concatenate([np.zeros(RATE // 2), sig, np.zeros(RATE // 2)])
                x += rng.normal(0, 10 ** (-60 / 20), len(x))
                found = detect(x[rng.integers(0, BLOCK):])
                hits += pad in found
                wrong += any(p != pad for p in found)
            results.append(f"{pad}: {hits}/10" + (f" ({wrong} wrong)" if wrong else ""))
        print(f"{style:11s}", "  ".join(results))


if __name__ == "__main__":
    main()
