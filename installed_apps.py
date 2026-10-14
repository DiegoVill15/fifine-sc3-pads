"""List Start menu apps (desktop and Microsoft Store) so they can be picked by name."""
import json
import re
import subprocess

APPS_FOLDER = "shell:AppsFolder\\"
SKIP = re.compile(r"uninstall|desinstal|readme|léame|help|ayuda|support|soporte", re.I)


def list_apps():
    """Return {name: path} sorted by name; the path opens with os.startfile."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
         "Get-StartApps | ConvertTo-Json -Compress"],
        capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    entries = json.loads(out.stdout.decode("utf-8") or "[]")
    if isinstance(entries, dict):
        entries = [entries]
    apps = {}
    for e in entries:
        name, app_id = (e.get("Name") or "").replace("\xa0", " ").strip(), e.get("AppID") or ""
        if not name or not app_id or SKIP.search(name) or app_id.startswith(("http:", "https:")):
            continue
        apps.setdefault(name, APPS_FOLDER + app_id)
    return dict(sorted(apps.items(), key=lambda kv: kv[0].lower()))


if __name__ == "__main__":
    for name, path in list_apps().items():
        print(f"{name:40s} {path}")
