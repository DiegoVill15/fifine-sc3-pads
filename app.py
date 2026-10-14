"""SC3 Pads: configure the Fifine SC3 CUSTOM A–D pads and run their actions.

Usage: pythonw app.py            open the window
       pythonw app.py --start    open minimized with the detector running (start with Windows)
"""
import os
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import sounddevice as sd

import keys
from actions import PARAM_KEY, Obs, load_config, run_action, save_config
from audio import PAD_TONES, find_sc3, init_audio_thread, output_device, play_signature
from detector import BLOCK_S, Detector
from installed_apps import APPS_FOLDER, list_apps

HERE = Path(__file__).parent
STARTUP = (Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
           / "SC3 Pads.vbs")

ACTION_TYPES = {                  # key in actions.json -> label on screen
    "none": "No action",
    "open": "Open app or file",
    "keys": "Keyboard shortcut",
    "obs_scene": "OBS: switch scene",
    "obs_record": "OBS: start/stop recording",
    "obs_stream": "OBS: start/stop streaming",
    "obs_mute": "OBS: mute/unmute source",
    "command": "Windows command",
}
ACTION_LABELS = {v: k for k, v in ACTION_TYPES.items()}
SUGGESTED_KEYS = ["play_pause", "next_track", "prev_track", "volume_mute", "volume_up",
                  "volume_down", "ctrl+shift+f9", "ctrl+shift+f10"]
STYLE_LABELS = {"beep": "Beep", "bell": "Bell", "transition": "Transition"}

TK_KEYS = {"space": "space", "return": "enter", "tab": "tab", "escape": "esc",
           "backspace": "backspace", "up": "up", "down": "down", "left": "left",
           "right": "right", "home": "home", "end": "end", "prior": "pageup",
           "next": "pagedown", "insert": "insert", "delete": "delete", "pause": "pause"}
MODIFIER_KEYSYMS = {"control_l", "control_r", "shift_l", "shift_r", "alt_l", "alt_r",
                    "win_l", "win_r", "super_l", "super_r", "caps_lock"}
GREEN, RED = "#2e7d32", "#c62828"


class DetectorThread(threading.Thread):
    """Listens to the SC3 and tells the UI (through events) whenever a pad plays."""

    def __init__(self, events):
        super().__init__(daemon=True)
        self.events = events
        self.stop_flag = threading.Event()
        self.mute_until = 0.0  # detections are ignored while a pad is being recorded

    def run(self):
        init_audio_thread()
        try:
            idx, dev = find_sc3("input")
            rate = int(dev["default_samplerate"])
            detector = Detector(rate)
            blocks = queue.Queue()
            with sd.InputStream(device=idx, samplerate=rate, channels=dev["max_input_channels"],
                                dtype="float32", blocksize=int(rate * BLOCK_S),
                                callback=lambda d, f, t, s: blocks.put(d.mean(axis=1).copy())):
                self.events.put(("status", f"Listening on “{dev['name']}”"))
                while not self.stop_flag.is_set():
                    try:
                        data = blocks.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    pad = detector.feed(data)
                    if pad and time.monotonic() > self.mute_until:
                        self.events.put(("pad", pad))
        except Exception as exc:
            self.events.put(("error", f"Detector stopped: {exc}"))
        finally:
            self.events.put(("stopped", None))


class PadRow:
    def __init__(self, app, parent, pad, row):
        self.app, self.pad = app, pad
        cfg = app.config.get(pad, {})
        sound = cfg.get("sound", {})

        self.frame = ttk.LabelFrame(parent, text=f"  Pad {pad}  ", padding=8)
        self.frame.grid(row=row, column=0, sticky="ew", pady=4)
        self.frame.columnconfigure(1, weight=1)

        self.kind = tk.StringVar(value=ACTION_TYPES.get(cfg.get("type", "none"), "No action"))
        box = ttk.Combobox(self.frame, textvariable=self.kind, values=list(ACTION_TYPES.values()),
                           state="readonly", width=28)
        box.grid(row=0, column=0, sticky="w")
        box.bind("<<ComboboxSelected>>", lambda e: self.on_kind_changed())

        self.param = tk.StringVar(value=cfg.get(PARAM_KEY.get(cfg.get("type"), ""), ""))
        # For "open": what is shown (app name or path) and its dropdown list.
        self.app_name = tk.StringVar(value=cfg.get("name") or self.param.get())
        self.app_name.trace_add("write", lambda *a: self.param.set(
            self.app.installed_apps.get(self.app_name.get(), self.app_name.get())))
        self.app_box = None
        self.param_frame = ttk.Frame(self.frame)
        self.param_frame.grid(row=0, column=1, sticky="ew", padx=8)
        self.param_frame.columnconfigure(0, weight=1)

        ttk.Button(self.frame, text="Test action", command=self.test_action).grid(row=0, column=2)

        sound_row = ttk.Frame(self.frame)
        sound_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Label(sound_row, text="Sound:").pack(side="left")
        self.style = tk.StringVar(value=STYLE_LABELS.get(sound.get("style"), "Bell"))
        ttk.Combobox(sound_row, textvariable=self.style, values=list(STYLE_LABELS.values()),
                     state="readonly", width=11).pack(side="left", padx=4)
        ttk.Label(sound_row, text="Volume:").pack(side="left", padx=(8, 0))
        self.volume = tk.IntVar(value=int(sound.get("volume", 50)))
        slider = tk.DoubleVar(value=self.volume.get())
        ttk.Scale(sound_row, from_=10, to=100, variable=slider, length=120,
                  command=lambda v: self.volume.set(round(float(v) / 5) * 5)).pack(side="left", padx=4)
        ttk.Label(sound_row, textvariable=self.volume, width=4).pack(side="left")
        ttk.Button(sound_row, text="Preview", command=self.preview).pack(side="left", padx=4)
        self.record_btn = ttk.Button(sound_row, text="Record to pad", command=self.record)
        self.record_btn.pack(side="left")
        self.status = ttk.Label(sound_row, text="", foreground=GREEN)
        self.status.pack(side="left", padx=10)

        for var in (self.kind, self.param, self.style, self.volume):
            var.trace_add("write", lambda *a: app.schedule_save())
        self.on_kind_changed(initial=True)

    # --- config ----------------------------------------------------------------------
    def kind_key(self):
        return ACTION_LABELS[self.kind.get()]

    def style_key(self):
        return {v: k for k, v in STYLE_LABELS.items()}[self.style.get()]

    def to_config(self):
        kind = self.kind_key()
        cfg = {"type": kind}
        if kind in PARAM_KEY:
            cfg[PARAM_KEY[kind]] = self.param.get().strip()
        if kind == "open" and self.app_name.get() in self.app.installed_apps:
            cfg["name"] = self.app_name.get()
        cfg["sound"] = {"style": self.style_key(), "volume": self.volume.get()}
        return cfg

    def on_kind_changed(self, initial=False):
        for child in self.param_frame.winfo_children():
            child.destroy()
        if not initial:
            self.param.set("")
            self.app_name.set("")
        kind = self.kind_key()
        self.app_box = None
        if kind == "open":
            self.app_box = ttk.Combobox(self.param_frame, textvariable=self.app_name,
                                        values=list(self.app.installed_apps), height=15)
            self.app_box.grid(row=0, column=0, sticky="ew")
            self.app_box.bind("<KeyRelease>", self.filter_apps)
            ttk.Button(self.param_frame, text="Browse…", command=self.browse).grid(row=0, column=1, padx=(4, 0))
            self.show_app_name()
        elif kind == "keys":
            ttk.Combobox(self.param_frame, textvariable=self.param, values=SUGGESTED_KEYS).grid(
                row=0, column=0, sticky="ew")
            ttk.Button(self.param_frame, text="Capture…", command=self.capture_keys).grid(row=0, column=1, padx=(4, 0))
        elif kind in ("obs_scene", "obs_mute"):
            values = self.app.obs_scenes if kind == "obs_scene" else self.app.obs_inputs
            ttk.Combobox(self.param_frame, textvariable=self.param, values=values).grid(
                row=0, column=0, sticky="ew")
        elif kind == "command":
            ttk.Entry(self.param_frame, textvariable=self.param).grid(row=0, column=0, sticky="ew")

    def refresh_obs_lists(self):
        if self.kind_key() in ("obs_scene", "obs_mute"):
            self.on_kind_changed(initial=True)

    def filter_apps(self, event):
        """While typing, the list only shows apps whose name contains the text."""
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        text = self.app_name.get().lower()
        self.app_box.configure(values=[n for n in self.app.installed_apps if text in n.lower()])

    def show_app_name(self):
        """If the saved path belongs to an installed app, show its name."""
        path = self.param.get().lower()
        for name, app_path in self.app.installed_apps.items():
            if path in (app_path.lower(), app_path[len(APPS_FOLDER):].lower()):
                if self.app_name.get() != name:
                    self.app_name.set(name)
                    self.param.set(app_path)
                return

    def refresh_app_list(self):
        if self.app_box is not None:
            self.app_box.configure(values=list(self.app.installed_apps))
            self.show_app_name()

    def browse(self):
        path = filedialog.askopenfilename(
            title=f"Choose what pad {self.pad} opens",
            filetypes=[("Programs and shortcuts", "*.exe *.lnk *.bat *.cmd *.url"), ("All files", "*.*")])
        if path:
            self.app_name.set(os.path.normpath(path))

    def capture_keys(self):
        win = tk.Toplevel(self.app.root)
        win.title("Capture shortcut")
        win.transient(self.app.root)
        win.grab_set()
        ttk.Label(win, text="Press the shortcut you want to assign\n(for example Ctrl + Shift + F9)",
                  padding=20, justify="center").pack()
        win.focus_force()

        def on_key(event):
            sym = event.keysym.lower()
            if sym in MODIFIER_KEYSYMS:
                return
            name = TK_KEYS.get(sym, sym)
            if len(name) == 1 or name in keys.NAMED:
                mods = [m for m, bit in (("ctrl", 0x4), ("shift", 0x1), ("alt", 0x20000))
                        if event.state & bit]
                self.param.set("+".join(mods + [name]))
                win.destroy()
            return "break"

        win.bind("<KeyPress>", on_key)

    # --- buttons ---------------------------------------------------------------------
    def test_action(self):
        self.app.execute(self.pad, self.to_config(), manual=True)

    def preview(self):
        style, volume = self.style_key(), self.volume.get()
        threading.Thread(target=self.app.safe, daemon=True,
                         args=(play_signature, self.pad, style, volume,
                               sd.query_devices(kind="output")["index"])).start()

    def record(self):
        style, volume = self.style_key(), self.volume.get()
        self.record_btn.state(["disabled"])

        def countdown(n):
            if n > 0:
                self.status.config(text=f"Hold pad {self.pad} down… {n}", foreground=RED)
                self.app.root.after(1000, countdown, n - 1)
                return
            self.status.config(text="Recording sound…")
            self.app.mute_detector(seconds=3)
            threading.Thread(target=play_then_release, daemon=True).start()

        def play_then_release():
            self.app.safe(lambda: play_signature(self.pad, style, volume, output_device()[0]))
            self.app.events.put(("recorded", self.pad))

        countdown(3)

    def recorded(self):
        self.record_btn.state(["!disabled"])
        self.status.config(text="Done: release the pad, then press it to test", foreground=GREEN)

    def flash(self, text):
        self.status.config(text=text, foreground=GREEN)
        ttk.Style().configure("Hit.TLabelframe.Label", foreground=GREEN, font=("Segoe UI", 9, "bold"))
        self.frame.configure(style="Hit.TLabelframe")
        self.app.root.after(1200, lambda: self.frame.configure(style="TLabelframe"))


class App:
    def __init__(self, root, autostart):
        self.root = root
        self.config = load_config()
        self.events = queue.Queue()
        self.detector = None
        self.obs = Obs(self.config.get("obs_port", 4455))
        self.obs_scenes, self.obs_inputs = [], []
        self.installed_apps = {}
        self.save_pending = None

        root.title("SC3 Pads – Fifine SC3 CUSTOM buttons")
        root.minsize(760, 0)
        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        top = ttk.Frame(main)
        top.grid(row=0, column=0, sticky="ew")
        self.obs_label = ttk.Label(top, text="OBS: not connected")
        self.obs_label.pack(side="left")
        ttk.Button(top, text="Connect / refresh OBS", command=self.refresh_obs).pack(side="left", padx=8)
        self.autostart = tk.BooleanVar(value=STARTUP.exists())
        ttk.Checkbutton(top, text="Start with Windows", variable=self.autostart,
                        command=self.toggle_autostart).pack(side="right")

        pads = ttk.Frame(main)
        pads.grid(row=1, column=0, sticky="ew", pady=6)
        pads.columnconfigure(0, weight=1)
        self.rows = {pad: PadRow(self, pads, pad, i) for i, pad in enumerate(PAD_TONES)}

        det = ttk.LabelFrame(main, text="  Detector  ", padding=8)
        det.grid(row=2, column=0, sticky="nsew")
        main.rowconfigure(2, weight=1)
        bar = ttk.Frame(det)
        bar.pack(fill="x")
        self.run_btn = ttk.Button(bar, text="▶ Start", command=self.toggle_detector)
        self.run_btn.pack(side="left")
        self.test_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Test only (show detections without running actions)",
                        variable=self.test_only).pack(side="left", padx=10)
        self.det_label = ttk.Label(bar, text="Stopped")
        self.det_label.pack(side="right")
        self.log_box = tk.Text(det, height=8, state="disabled", font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True, pady=(6, 0))

        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll_events)
        self.refresh_obs(quiet=True)
        threading.Thread(target=lambda: self.events.put(("apps", self.safe(list_apps) or {})),
                         daemon=True).start()
        if autostart:
            self.toggle_detector()
            root.iconify()

    # --- helpers ---------------------------------------------------------------------
    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{time.strftime('%H:%M:%S')}  {text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def safe(self, fn, *args):
        """Run fn on a worker thread, sending errors to the log instead of crashing."""
        init_audio_thread()
        try:
            return fn(*args)
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def schedule_save(self):
        if self.save_pending:
            self.root.after_cancel(self.save_pending)
        self.save_pending = self.root.after(500, self.save)

    def save(self):
        self.save_pending = None
        cfg = {"obs_port": self.config.get("obs_port", 4455)}
        cfg.update({pad: row.to_config() for pad, row in self.rows.items()})
        self.config = cfg
        save_config(cfg)

    # --- OBS -------------------------------------------------------------------------
    def refresh_obs(self, quiet=False):
        def work():
            try:
                scenes = self.obs.call(lambda c: c.get_scene_list().scenes)
                inputs = self.obs.call(lambda c: c.get_input_list().inputs)
                self.events.put(("obs", ([s["sceneName"] for s in reversed(scenes)],
                                         [i["inputName"] for i in inputs])))
            except Exception as exc:
                self.events.put(("obs_error", None if quiet else str(exc)))
        threading.Thread(target=work, daemon=True).start()

    # --- actions ---------------------------------------------------------------------
    def execute(self, pad, cfg, manual=False):
        kind = cfg.get("type", "none")
        if kind == "none":
            if manual:
                self.log(f"Pad {pad}: no action assigned")
            return
        if kind in PARAM_KEY and not cfg.get(PARAM_KEY[kind]):
            self.log(f"Pad {pad}: “{ACTION_TYPES[kind]}” is not filled in")
            return
        detail = cfg.get("name") or cfg.get(PARAM_KEY.get(kind, ""), "")
        self.log(f"Pad {pad} → {ACTION_TYPES[kind]}" + (f": {detail}" if detail else ""))
        if kind == "keys" and manual:
            self.log("  (sending in 3 s: switch to the window where you want to try it)")

        def work():
            if kind == "keys" and manual:
                time.sleep(3)
            self.safe(run_action, cfg, self.obs)
        threading.Thread(target=work, daemon=True).start()

    # --- detector --------------------------------------------------------------------
    def toggle_detector(self):
        if self.detector:
            self.detector.stop_flag.set()
            self.run_btn.state(["disabled"])
            return
        self.detector = DetectorThread(self.events)
        self.detector.start()
        self.run_btn.config(text="■ Stop")
        self.det_label.config(text="Starting…")

    def mute_detector(self, seconds):
        if self.detector:
            self.detector.mute_until = time.monotonic() + seconds

    # --- start with Windows ----------------------------------------------------------
    def toggle_autostart(self):
        try:
            if self.autostart.get():
                pythonw = HERE / ".venv/Scripts/pythonw.exe"
                STARTUP.write_text(
                    'CreateObject("WScript.Shell").Run """{}"" ""{}"" --start", 0\n'.format(
                        pythonw, HERE / "app.py"), encoding="utf-8")
                self.log("Will start with Windows (minimized, detector running)")
            elif STARTUP.exists():
                STARTUP.unlink()
                self.log("Will no longer start with Windows")
        except OSError as exc:
            messagebox.showerror("SC3 Pads", f"Could not change start with Windows:\n{exc}")

    # --- event loop ------------------------------------------------------------------
    def poll_events(self):
        while True:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "pad":
                row = self.rows[data]
                row.flash("Detected!")
                if self.test_only.get():
                    self.log(f"Pad {data} detected (test only: nothing runs)")
                else:
                    self.execute(data, row.to_config())
            elif kind == "status":
                self.det_label.config(text=data)
                self.log(data)
            elif kind == "stopped":
                self.detector = None
                self.run_btn.config(text="▶ Start")
                self.run_btn.state(["!disabled"])
                self.det_label.config(text="Stopped")
            elif kind == "recorded":
                self.rows[data].recorded()
            elif kind == "apps":
                self.installed_apps = data
                for row in self.rows.values():
                    row.refresh_app_list()
            elif kind == "obs":
                self.obs_scenes, self.obs_inputs = data
                self.obs_label.config(text=f"OBS: connected ({len(self.obs_scenes)} scenes)",
                                      foreground=GREEN)
                for row in self.rows.values():
                    row.refresh_obs_lists()
            elif kind == "obs_error":
                self.obs_label.config(text="OBS: not connected", foreground=RED)
                if data:
                    self.log(data)
            elif kind == "error":
                self.log(f"Error: {data}")
        self.root.after(100, self.poll_events)

    def close(self):
        if self.save_pending:
            self.root.after_cancel(self.save_pending)
            self.save()
        if self.detector:
            self.detector.stop_flag.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        App(root, autostart="--start" in sys.argv)
        root.mainloop()
    except Exception:
        (HERE / "app-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        messagebox.showerror("SC3 Pads", "Something went wrong. Details in app-error.log")
        raise


if __name__ == "__main__":
    main()
