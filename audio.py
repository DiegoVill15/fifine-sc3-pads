"""Audio helpers: SC3 devices, pad sound signatures and tone analysis."""
import ctypes

import numpy as np
import sounddevice as sd

# Each pad is identified by a perfect fifth (two notes that sound good together).
# Two simultaneous pure tones make it very unlikely that voice or music triggers a pad.
PAD_TONES = {
    "A": (1047, 1568),  # C6 + G6
    "B": (1175, 1760),  # D6 + A6
    "C": (1319, 1976),  # E6 + B6
    "D": (1397, 2093),  # F6 + C7
}
ALL_FREQS = sorted({f for pair in PAD_TONES.values() for f in pair})
STYLES = ("beep", "bell", "transition")


def init_audio_thread():
    """Initialize COM on the current thread: WASAPI fails on worker threads without it."""
    ctypes.windll.ole32.CoInitializeEx(None, 0)


def find_sc3(kind):
    """kind: 'input' (SC3 microphone) or 'output' (SC3 speakers), via WASAPI."""
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    for api in sd.query_hostapis():
        if api["name"] != "Windows WASAPI":
            continue
        for idx in api["devices"]:
            dev = sd.query_devices(idx)
            if "fifine SC3" in dev["name"] and dev[key] > 0:
                return idx, dev
    raise RuntimeError(f"Fifine SC3 {kind} not found (WASAPI). Is the console connected?")


def output_device():
    """The SC3 output, or the default output if it is busy (e.g. held by Voicemeeter).

    Returns (index, device, used_fallback).
    """
    idx, dev = find_sc3("output")
    try:
        sd.check_output_settings(device=idx, samplerate=dev["default_samplerate"], channels=2)
        with sd.OutputStream(device=idx, samplerate=dev["default_samplerate"], channels=2):
            pass
        return idx, dev, False
    except sd.PortAudioError:
        dev = sd.query_devices(kind="output")
        return dev["index"], dev, True


def _dyad(pad, rate, seconds):
    lo, hi = PAD_TONES[pad]
    t = np.arange(int(rate * seconds)) / rate
    return 0.5 * (np.sin(2 * np.pi * lo * t) + np.sin(2 * np.pi * hi * t)), t


def _bell(pad, rate):
    """Both notes held ~0.35 s, then a soft fade.

    The extra partials (x2.76, typical of a bell) sit above 2.8 kHz, far from the
    frequencies the detector looks at. The pad trims ~0.1 s from the start of a
    recording, so the steady part lasts much longer than the detector needs.
    """
    tone, t = _dyad(pad, rate, 0.9)
    lo, hi = PAD_TONES[pad]
    shimmer = 0.12 * (np.sin(2 * np.pi * lo * 2.76 * t) + np.sin(2 * np.pi * hi * 2.76 * t))
    env = np.where(t < 0.35, 1.0, np.exp(-(t - 0.35) / 0.15))
    env[: int(rate * 0.005)] = np.linspace(0, 1, int(rate * 0.005))
    return tone * env + shimmer * np.exp(-t / 0.12)


def _whoosh(rate, seconds=0.35, seed=0):
    """Rising noise burst with no energy between 450 Hz and 2.6 kHz (the signature band)."""
    n = int(rate * seconds)
    spec = np.fft.rfft(np.random.default_rng(seed).normal(0, 1, n))
    f = np.fft.rfftfreq(n, 1 / rate)
    spec[(f > 450) & (f < 2600)] = 0
    spec[f > 9000] = 0
    noise = np.fft.irfft(spec, n)
    noise /= np.abs(noise).max()
    t = np.arange(n) / n
    return noise * (t ** 2) * 0.6


def make_signature(pad, rate, style="bell", level=0.35):
    if style == "beep":
        tone, _ = _dyad(pad, rate, 0.4)
        fade = int(rate * 0.01)
        env = np.ones_like(tone)
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
        sound = tone * env
    elif style == "bell":
        sound = _bell(pad, rate)
    elif style == "transition":
        sound = np.concatenate([_whoosh(rate), _bell(pad, rate)])
    else:
        raise ValueError(f"unknown style: {style}")
    return (level * sound / np.abs(sound).max()).astype("float32")


def play_signature(pad, style="bell", volume=50, device=None):
    """Play a pad signature and wait until it ends. device=None uses output_device()."""
    if device is None:
        device = output_device()[0]
    rate = int(sd.query_devices(device)["default_samplerate"])
    sig = make_signature(pad, rate, style, level=0.35 * volume / 100)
    with sd.OutputStream(device=device, samplerate=rate, channels=2, dtype="float32") as out:
        out.write(np.ascontiguousarray(np.column_stack([sig, sig])))


NEIGHBOR_OFFSETS = (-170, -140, -110, -80, 80, 110, 140, 170)


def tone_snr(block, rate, freqs):
    """For each frequency: (tone power / mean power at neighboring frequencies, amplitude).

    A pure tone scores high even under louder voice or music, because those spread
    their energy into the neighbors too. With a 40 ms window, ±80 Hz is outside the
    tone's main lobe.
    """
    n = len(block)
    t = np.arange(n) / rate
    win = block * np.hanning(n)

    def power(f):
        return abs((win * np.exp(-2j * np.pi * f * t)).sum()) ** 2

    out = {}
    for f in freqs:
        p = power(f)
        around = sum(power(f + d) for d in NEIGHBOR_OFFSETS) / len(NEIGHBOR_OFFSETS)
        amplitude = 4 * np.sqrt(p) / n   # sine amplitude (Hann window gain is n/4)
        out[f] = (p / (around + 1e-20), amplitude)
    return out
