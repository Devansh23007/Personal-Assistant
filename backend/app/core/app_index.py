"""Cached index of apps installed in Windows Start menu and uninstall registry."""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import os
from pathlib import Path
import subprocess
import threading
import time


@dataclass(frozen=True)
class InstalledApp:
    name: str
    app_id: str | None = None
    shortcut: str | None = None
    executable: str | None = None


_lock = threading.RLock()
_apps: dict[str, InstalledApp] = {}
_last_refresh = 0.0
_refresh_thread_started = False
REFRESH_SECONDS = 300


def _key(value: str) -> str:
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in value).split())


def _match_score(query: str, candidate: str) -> float:
    ratio = difflib.SequenceMatcher(None, query, candidate).ratio()
    if len(query) >= 4 and (candidate.startswith(query + " ") or (" " + query + " ") in (" " + candidate + " ")):
        ratio = max(ratio, 0.9)
    q_tokens, c_tokens = set(query.split()), set(candidate.split())
    if q_tokens and q_tokens.issubset(c_tokens):
        ratio = max(ratio, 0.86)
    return ratio


def refresh_installed_app_index() -> int:
    """Refresh the cached app list. Slow OS enumeration happens only here."""
    global _apps, _last_refresh
    collected: dict[str, InstalledApp] = {}
    if os.name == "nt":
        script = r"""$ErrorActionPreference='SilentlyContinue'; $rows=@(); Get-StartApps | ForEach-Object { $rows += [pscustomobject]@{name=$_.Name; app_id=$_.AppID} }; $rows | ConvertTo-Json -Compress"""
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
                capture_output=True, text=True, timeout=20, check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                rows = json.loads(result.stdout)
                if isinstance(rows, dict):
                    rows = [rows]
                for row in rows:
                    name = str(row.get("name") or "").strip()
                    if name:
                        collected[_key(name)] = InstalledApp(name=name, app_id=str(row.get("app_id") or "") or None)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass

        start_menu_dirs = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        for root in start_menu_dirs:
            if not root.is_dir():
                continue
            try:
                for shortcut in root.rglob("*.lnk"):
                    name = shortcut.stem
                    collected.setdefault(_key(name), InstalledApp(name=name, shortcut=str(shortcut)))
            except OSError:
                continue

        # Registry names improve matching when an installed program has no Start shortcut.
        try:
            import winreg
            uninstall_paths = (
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            )
            for hive, path in uninstall_paths:
                try:
                    with winreg.OpenKey(hive, path) as root:
                        for index in range(winreg.QueryInfoKey(root)[0]):
                            try:
                                with winreg.OpenKey(root, winreg.EnumKey(root, index)) as item:
                                    name = str(winreg.QueryValueEx(item, "DisplayName")[0]).strip()
                                    if name:
                                        executable = None
                                        try:
                                            icon = os.path.expandvars(str(winreg.QueryValueEx(item, "DisplayIcon")[0]))
                                            candidate = icon.strip().strip(chr(34)).split(",")[0].strip().strip(chr(34))
                                            if os.path.isfile(candidate):
                                                executable = candidate
                                        except OSError:
                                            pass
                                        collected.setdefault(_key(name), InstalledApp(name=name, executable=executable))
                            except OSError:
                                continue
                except OSError:
                    continue
        except ImportError:
            pass

    # Keep useful command-launchable apps indexed on non-Windows hosts too.
    if os.name != "nt":
        from app.core.app_launcher import APP_ALIASES, COMMAND_ALIASES
        for alias, canonical in APP_ALIASES.items():
            collected.setdefault(_key(canonical), InstalledApp(name=canonical))
        for alias, command in COMMAND_ALIASES.items():
            if __import__("shutil").which(command[0]):
                collected.setdefault(_key(alias), InstalledApp(name=alias, executable=command[0]))

    with _lock:
        _apps = collected
        _last_refresh = time.monotonic()
        return len(_apps)


def ensure_app_index() -> None:
    with _lock:
        stale = time.monotonic() - _last_refresh > REFRESH_SECONDS
    if stale:
        refresh_installed_app_index()


def start_app_index_refresh() -> None:
    global _refresh_thread_started
    with _lock:
        if _refresh_thread_started:
            return
        _refresh_thread_started = True

    def refresh_loop() -> None:
        while True:
            time.sleep(REFRESH_SECONDS)
            refresh_installed_app_index()

    threading.Thread(target=refresh_loop, name="viper-app-index-refresh", daemon=True).start()


def find_installed_app(name: str, aliases: dict[str, str] | None = None) -> InstalledApp | None:
    ensure_app_index()
    query = _key(name)
    if not query:
        return None
    if aliases:
        alias = aliases.get(" ".join(name.lower().split()))
        if alias:
            query = _key(alias)
    with _lock:
        if query in _apps:
            return _apps[query]
        best_key = max(_apps, key=lambda candidate: _match_score(query, candidate), default="")
        score = _match_score(query, best_key) if best_key else 0
        if score < 0.78:
            return None
        # Avoid guessing between similarly-scored installed targets.
        ranked = sorted(((_match_score(query, key), key) for key in _apps), reverse=True)
        if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.035 and ranked[1][0] >= 0.78:
            return None
        return _apps[best_key]


WEB_SERVICES = {
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "spotify": "https://open.spotify.com",
    "discord": "https://discord.com/app",
    "whatsapp": "https://web.whatsapp.com",
    "microsoft teams": "https://teams.microsoft.com",
    "teams": "https://teams.microsoft.com",
}


def get_app_preference(name: str) -> str | None:
    import json
    path = Path(__file__).resolve().parents[2] / "storage" / "open_preferences.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get(_key(name))
        return value if value in {"app", "web"} else None
    except (OSError, ValueError, AttributeError):
        return None


def set_app_preference(name: str, kind: str) -> None:
    import json
    if kind not in {"app", "web"}:
        return
    path = Path(__file__).resolve().parents[2] / "storage" / "open_preferences.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data[_key(name)] = kind
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
