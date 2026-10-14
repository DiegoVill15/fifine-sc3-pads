# SC3 Pads

Turn the four **CUSTOM** pads (A–D) of the **Fifine AmpliGame SC3** mixer into macro buttons on Windows: switch OBS scenes, start/stop recording or streaming, mute sources, open apps, or send keyboard shortcuts.

## Why it works through sound

The CUSTOM pads are a standalone sampler: each one records up to 15 seconds of audio and plays it back. Fifine provides no software to remap them, and **pressing a pad sends nothing to the PC over USB**. This was checked by reading both of the SC3's HID interfaces (the media-keys one and the vendor one), both passively and by polling, while pressing the pads. It was also checked by statically analyzing the vendor's firmware updater. Only volume and media controls reach Windows as events.

What *does* reach the PC is the pad's **audio**. When you press a pad, its recording is mixed into the SC3's USB microphone signal. So SC3 Pads works like this:

1. You record a short sound into each pad (the app plays it for you while you hold the pad down).
2. Each sound contains a unique **signature**: two pure notes forming a perfect fifth (A = C6+G6, B = D6+A6, C = E6+B6, D = F6+C7).
3. The app listens to the *Microphone (fifine SC3)* input. When it hears a pad's signature, it runs that pad's action.

The detector compares each note with the frequencies around it, so a pure tone stands out even under voice or music. It also requires the signature to hold for over 100 ms and to be very clean at least once. In tests with loud simulated music it never triggered by mistake. Audio played by the PC (games, music, videos) does not get into the SC3 microphone input, so it does not interfere either.

There are three sound styles: **Beep** (short and discreet), **Bell** (a soft notification-like chime) and **Transition** (a whoosh followed by the chime, handy for scene changes).

## Requirements

- Windows 10 or 11
- Fifine SC3 connected over USB
- [Python 3.10+](https://www.python.org/downloads/) (check *Add python.exe to PATH* during setup)
- Optional: [OBS Studio](https://obsproject.com/) 28+ for the OBS actions

## Install

1. Download this repository (green **Code** button → *Download ZIP*) and extract it.
2. Double-click **`install.cmd`**. It creates a local Python environment in `.venv` and installs the dependencies.
3. Double-click **`SC3 Pads.cmd`** to open the app.

## Usage

For each pad:

1. **Choose the action** and fill in its detail:

   | Action | Detail |
   |---|---|
   | Open app or file | Pick from your installed apps (type to search), or *Browse…* for any file |
   | Keyboard shortcut | e.g. `ctrl+shift+f9`, or *Capture…* to press it; media keys like `play_pause`, `next_track`, `volume_mute` |
   | OBS: switch scene / mute source | Pick from your OBS scenes and sources |
   | OBS: start/stop recording or streaming | — |
   | Windows command | Any command line |

2. **Choose the sound** (style and volume). *Preview* plays it on your speakers.
3. Click **Record to pad**, and when the countdown starts **hold the pad down** until the message tells you to release it.

Then click **▶ Start** in the *Detector* panel and press the pads. Turn on *Test only* to see detections without running the actions. Changes are saved automatically to `actions.json` (see [`actions.example.json`](actions.example.json) for the format).

**Start with Windows** opens the app minimized with the detector running whenever you log in.

### OBS setup

In OBS go to **Tools → WebSocket Server Settings** and check **Enable WebSocket server**. The app reads the password from OBS's own settings file, so you never have to copy it. Then click **Connect / refresh OBS**.

## Limitations

- **The pad sound is still played.** You will hear it in your headphones, and it is part of the SC3 microphone signal, so your stream hears it too if your mic source is the SC3. Keep the volume low and choose the style you like. The detector works at low volumes.
- If a lot of noise gets into the microphone at the exact moment you press a pad, that press may be missed. The detector prefers missing a press over triggering one you didn't make.
- Some games with anti-cheat ignore simulated keyboard shortcuts. OBS global hotkeys, Discord and the desktop do receive them.

## Troubleshooting

- **A pad is not detected:** record its sound again. The pad must be held down *before* the sound starts. Use *Test only* to check.
- **"Fifine SC3 input not found":** the console is unplugged, or Windows renamed the device. It must appear as *Microphone (fifine SC3)* in Sound settings.
- **The SC3 output is busy (Voicemeeter):** if Voicemeeter or another app holds *Speakers (fifine SC3)* exclusively, the app plays the sound through your default output instead. Make sure that output is routed to the SC3 so the pad can record it.
- **A pad keeps blinking and won't record:** it is playing back its recording. Wait for it to finish, or unplug the SC3 for a few seconds.
- **The app does not open:** see `app-error.log` in the app folder.

## Project layout

| File | Purpose |
|---|---|
| `app.py` | The window (Tkinter) |
| `detector.py` | Signature detection; `python detector.py --test` runs it from the console |
| `audio.py` | SC3 devices, signature sounds and tone analysis |
| `actions.py` | Actions, OBS connection and `actions.json` |
| `keys.py` | Sends keyboard shortcuts |
| `installed_apps.py` | Lists Start menu apps |
| `tools/simulate.py` | Measures detection and false triggers with simulated music |
| `tools/make_samples.py` | Writes every sound as a WAV file to `samples/` |

## How this was researched

Before settling on audio, the SC3's USB interfaces were tested and the vendor's firmware updater was statically analyzed with [REA](https://github.com/morluto/rea) (reverse-engineering MCP server) and Ghidra. Neither revealed a way to read the pads, which is why SC3 Pads uses sound. REA is not needed to use this project.

## License

[MIT](LICENSE) © [DiegoVill15](https://github.com/DiegoVill15)

## Disclaimer

Not affiliated with or endorsed by Fifine. SC3 Pads only reads the SC3's microphone input and plays sounds. It never writes to the device or modifies its firmware.
