"""Send keyboard shortcuts to Windows, e.g. "ctrl+shift+f9" or "play_pause".

Keys are lowercase and joined with "+". Some games with anti-cheat ignore simulated
keys; OBS (global hotkeys), Discord and the desktop do receive them.
"""
import ctypes
import time

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

MODIFIERS = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B}

NAMED = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "insert": 0x2D, "delete": 0x2E, "printscreen": 0x2C, "pause": 0x13,
    # Media keys
    "play_pause": 0xB3, "next_track": 0xB0, "prev_track": 0xB1, "stop": 0xB2,
    "volume_up": 0xAF, "volume_down": 0xAE, "volume_mute": 0xAD,
}
NAMED.update({f"num{d}": 0x60 + d for d in range(10)})
NAMED.update({f"f{n}": 0x6F + n for n in range(1, 25)})

# Keys Windows treats as "extended" (without the flag they arrive as numpad keys).
EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B,
            0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3}


def parse(combo):
    """Turn "ctrl+shift+f9" into a list of virtual-key codes."""
    codes = []
    for part in combo.lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in MODIFIERS:
            codes.append(MODIFIERS[part])
        elif part in NAMED:
            codes.append(NAMED[part])
        elif len(part) == 1 and part.isalnum():
            codes.append(ord(part.upper()))
        else:
            raise ValueError(f"unknown key: {part!r}")
    if not codes:
        raise ValueError("the shortcut is empty")
    return codes


def _key(code, up):
    flags = (KEYEVENTF_EXTENDEDKEY if code in EXTENDED else 0) | (KEYEVENTF_KEYUP if up else 0)
    ctypes.windll.user32.keybd_event(code, 0, flags, 0)


def send(combo):
    codes = parse(combo)
    for code in codes:
        _key(code, up=False)
        time.sleep(0.01)
    time.sleep(0.03)
    for code in reversed(codes):
        _key(code, up=True)
        time.sleep(0.01)
