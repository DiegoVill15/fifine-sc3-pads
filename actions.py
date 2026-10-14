"""Pad actions (apps, shortcuts, OBS, commands) and the actions.json config file."""
import json
import os
import subprocess
import threading
from pathlib import Path

import keys

HERE = Path(__file__).parent
CONFIG = HERE / "actions.json"
DEFAULT_CONFIG = {"obs_port": 4455}

# action type -> name of its parameter in actions.json
PARAM_KEY = {"open": "path", "keys": "keys", "obs_scene": "scene", "obs_mute": "source",
             "command": "command"}


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def obs_password():
    """Read the password OBS itself stores, so it never has to be copied anywhere."""
    cfg = Path(os.environ["APPDATA"]) / "obs-studio/plugin_config/obs-websocket/config.json"
    try:
        return json.loads(cfg.read_text(encoding="utf-8")).get("server_password", "")
    except OSError:
        return ""


class Obs:
    """obs-websocket client that connects on demand and reconnects if OBS restarts."""

    def __init__(self, port):
        self.port = port
        self.client = None
        self.lock = threading.Lock()

    def call(self, fn):
        with self.lock:
            return self._call(fn)

    def _call(self, fn):
        import obsws_python as obs
        for attempt in (1, 2):
            try:
                if self.client is None:
                    self.client = obs.ReqClient(host="localhost", port=self.port,
                                                password=obs_password(), timeout=3)
                return fn(self.client)
            except Exception as exc:  # OBS closed or restarted: reconnect once
                self.client = None
                if attempt == 2:
                    raise RuntimeError(f"OBS is not responding ({exc}). "
                                       "Is it open with the WebSocket server enabled?")


def run_action(action, obs):
    kind = action.get("type", "none")
    if kind == "open":
        os.startfile(action["path"])
    elif kind == "keys":
        keys.send(action["keys"])
    elif kind == "obs_scene":
        obs.call(lambda c: c.set_current_program_scene(action["scene"]))
    elif kind == "obs_record":
        obs.call(lambda c: c.toggle_record())
    elif kind == "obs_stream":
        obs.call(lambda c: c.toggle_stream())
    elif kind == "obs_mute":
        obs.call(lambda c: c.toggle_input_mute(action["source"]))
    elif kind == "command":
        subprocess.Popen(action["command"], shell=True)
    elif kind != "none":
        raise ValueError(f"unknown action type: {kind!r}")
