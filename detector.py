"""Detects which pad was pressed by listening for its sound signature on the SC3 input.

Command line (the app does the same with a window):
    python detector.py          run the actions in actions.json
    python detector.py --test   only print detections, do not run anything
"""
import queue
import sys
import time
from collections import Counter, deque

import sounddevice as sd

from audio import ALL_FREQS, PAD_TONES, find_sc3, tone_snr

BLOCK_S = 0.04          # 40 ms -> 25 Hz resolution, enough to tell the signatures apart
WINDOW_BLOCKS = 6       # look at the last 240 ms...
MIN_BLOCKS = 3          # ...and the signature must appear in at least 3 (the pad trims the start)
MIN_SNR = 6             # each tone must be ~8 dB above the mean of its neighbor frequencies
PEAK_SNR = 100          # and 20 dB in at least one block: a pure tone gets there, voice/music don't
MIN_AMPLITUDE = 10 ** (-75 / 20)  # ignore tones quieter than -75 dBFS
COOLDOWN_S = 1.0        # minimum time between two triggers of the same pad


def classify(block, rate):
    """Return (pad, score) for the signature present in this block, or None."""
    tones = tone_snr(block, rate, ALL_FREQS)
    best = None
    for pad, (lo, hi) in PAD_TONES.items():
        (snr_lo, amp_lo), (snr_hi, amp_hi) = tones[lo], tones[hi]
        if min(snr_lo, snr_hi) < MIN_SNR or min(amp_lo, amp_hi) < MIN_AMPLITUDE:
            continue
        score = min(snr_lo, snr_hi)
        if best is None or score > best[1]:
            best = (pad, score)
    return best


class Detector:
    """Feed it audio blocks; it returns the pad once its signature is confirmed."""

    def __init__(self, rate):
        self.rate = rate
        self.recent = deque(maxlen=WINDOW_BLOCKS)
        self.blocks_seen = 0
        self.last_fire = {}

    def feed(self, block):
        self.blocks_seen += 1
        self.recent.append(classify(block, self.rate))
        counts = Counter(r[0] for r in self.recent if r)
        if not counts:
            return None
        pad, n = counts.most_common(1)[0]
        peak = max(r[1] for r in self.recent if r and r[0] == pad)
        now = self.blocks_seen * BLOCK_S
        if n < MIN_BLOCKS or peak < PEAK_SNR:
            return None
        if now - self.last_fire.get(pad, -COOLDOWN_S) < COOLDOWN_S:
            return None
        self.last_fire[pad] = now
        return pad


def main():
    from actions import Obs, load_config, run_action

    test = "--test" in sys.argv
    config = load_config()
    obs = Obs(config.get("obs_port", 4455))
    idx, dev = find_sc3("input")
    rate = int(dev["default_samplerate"])
    blocks = queue.Queue()
    detector = Detector(rate)
    print(f"Listening on [{idx}] {dev['name']} ({'test mode' if test else 'actions enabled'}). "
          "Ctrl+C to quit.")
    with sd.InputStream(device=idx, samplerate=rate, channels=dev["max_input_channels"],
                        dtype="float32", blocksize=int(rate * BLOCK_S),
                        callback=lambda d, f, t, s: blocks.put(d.mean(axis=1).copy())):
        while True:
            pad = detector.feed(blocks.get())
            if not pad:
                continue
            action = config.get(pad, {"type": "none"})
            print(f"{time.strftime('%H:%M:%S')}  pad {pad} detected -> {action.get('type')}",
                  flush=True)
            if not test:
                try:
                    run_action(action, obs)
                except Exception as exc:
                    print(f"  action failed: {exc}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
