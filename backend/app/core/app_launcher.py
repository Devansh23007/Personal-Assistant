"""Safe desktop app launching shared by J.A.R.V.I.S. and assistant tools."""

import base64
import os
import shutil
import subprocess
import sys


APP_ALIASES = {
    "google chrome": "Google Chrome",
    "chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "microsoft edge": "Microsoft Edge",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "code": "Visual Studio Code",
    "word": "Word",
    "microsoft word": "Word",
    "excel": "Excel",
    "microsoft excel": "Excel",
    "powerpoint": "PowerPoint",
    "power point": "PowerPoint",
    "outlook": "Outlook",
    "microsoft outlook": "Outlook",
    "notepad": "Notepad",
    "notes": "Notepad",
    "calculator": "Calculator",
    "calc": "Calculator",
    "file explorer": "File Explorer",
    "explorer": "File Explorer",
    "files": "File Explorer",
    "task manager": "Task Manager",
    "taskmgr": "Task Manager",
    "snipping tool": "Snipping Tool",
    "paint": "Paint",
    "spotify": "Spotify",
    "teams": "Microsoft Teams",
    "microsoft teams": "Microsoft Teams",
    "store": "Microsoft Store",
    "microsoft store": "Microsoft Store",
    "windows store": "Microsoft Store",
}

COMMAND_ALIASES = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "terminal": ["wt.exe"],
    "command prompt": ["cmd.exe"],
    "cmd": ["cmd.exe"],
    "explorer": ["explorer.exe"],
    "file explorer": ["explorer.exe"],
    "task manager": ["taskmgr.exe"],
    "taskmgr": ["taskmgr.exe"],
}


def launch_desktop_app(target: str) -> tuple[bool, str]:
    """Launch an installed app by Start menu name or a known command alias."""
    name = target.strip()
    if not name:
        return False, "Please name the app you want to open."

    normalized = " ".join(name.lower().split())
    if normalized in {"settings", "windows settings"} and os.name == "nt":
        try:
            os.startfile("ms-settings:")  # type: ignore[attr-defined]
            return True, "Opened Settings."
        except OSError as exc:
            return False, f"Couldn't open Settings: {exc}"

    command = COMMAND_ALIASES.get(normalized)
    if command:
        try:
            subprocess.Popen(command, shell=False)
            return True, f"Opened {name}."
        except OSError:
            # Some Windows apps are installed as packaged apps and only appear
            # in the Start menu registry, so try the registered app lookup below.
            pass

    app_name = APP_ALIASES.get(normalized, name)
    if os.name == "nt":
        encoded_name = base64.b64encode(app_name.encode("utf-8")).decode("ascii")
        script = rf"""
$name = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_name}'))
$app = Get-StartApps -ErrorAction SilentlyContinue | Where-Object {{ $_.Name -ieq $name }} | Select-Object -First 1
if ($app -and $app.AppID) {{
  Start-Process -FilePath "$env:WINDIR\explorer.exe" -ArgumentList @('shell:AppsFolder\' + $app.AppID)
  exit 0
}}
$cmd = Get-Command -CommandType Application -ErrorAction SilentlyContinue | Where-Object {{ $_.Name -ieq $name -or $_.Name -ieq ($name + '.exe') }} | Select-Object -First 1
if ($cmd) {{ Start-Process -FilePath $cmd.Source; exit 0 }}
exit 2
"""
        encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded_script],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if result.returncode == 0:
                return True, f"Opened {name}."
        except (OSError, subprocess.TimeoutExpired):
            pass
        return False, f"I couldn't find an installed app named '{name}'."

    executable = shutil.which(normalized)
    if executable:
        try:
            subprocess.Popen([executable], shell=False)
            return True, f"Opened {name}."
        except OSError as exc:
            return False, f"Couldn't open {name}: {exc}"
    return False, f"I couldn't find an installed app named '{name}' on {sys.platform}."
