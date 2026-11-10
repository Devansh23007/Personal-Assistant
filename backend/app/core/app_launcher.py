"""Safe desktop app launching shared by V.I.P.E.R. and assistant tools."""

import base64
import os
import re
import shutil
import subprocess
import sys
import webbrowser


APP_ALIASES = {
    "brave": "Brave",
    "brave browser": "Brave",
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


def open_url_with_preferred_browser(url: str, preferred_browser: str = "Brave") -> bool:
    """Open a URL in the requested browser, falling back to the OS default."""
    browser = preferred_browser.strip().lower()
    if browser == "brave":
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            shutil.which("brave.exe"),
            shutil.which("brave"),
            os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(program_files_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ]
        executable = next((candidate for candidate in candidates if candidate and os.path.isfile(candidate)), None)
        if executable:
            try:
                subprocess.Popen([executable, url], shell=False)
                return True
            except OSError:
                pass
    return bool(webbrowser.open(url))


def _run_hidden_powershell(script: str) -> bool:
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded_script],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def navigate_current_browser_tab(url: str, preferred_browser: str = "Brave") -> bool:
    """Navigate the active tab in the preferred browser without opening a new tab."""
    if os.name != "nt" or preferred_browser.strip().lower() != "brave":
        return False
    if not url.startswith(("https://", "http://")):
        url = "https://" + url
    encoded_url = base64.b64encode(url.encode("utf-8")).decode("ascii")
    encoded_browser = base64.b64encode(preferred_browser.encode("utf-8")).decode("ascii")
    script = rf"""
$url = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_url}'))
$browser = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_browser}'))
$shell = New-Object -ComObject WScript.Shell
if (-not $shell.AppActivate($browser)) {{ exit 2 }}
Start-Sleep -Milliseconds 150
$shell.SendKeys('^l')
Start-Sleep -Milliseconds 100
$escapedUrl = [regex]::Replace($url, '([+^%~(){{}}])', '{{$1}}')
$shell.SendKeys($escapedUrl)
$shell.SendKeys('{{ENTER}}')
exit 0
"""
    return _run_hidden_powershell(script)


def close_active_browser_tab(preferred_browser: str = "Brave") -> bool:
    """Close the active tab in the preferred browser using a normal Ctrl+W request."""
    if os.name != "nt" or preferred_browser.strip().lower() != "brave":
        return False
    encoded_browser = base64.b64encode(preferred_browser.encode("utf-8")).decode("ascii")
    script = rf"""
$browser = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_browser}'))
$shell = New-Object -ComObject WScript.Shell
if (-not $shell.AppActivate($browser)) {{ exit 2 }}
Start-Sleep -Milliseconds 150
$shell.SendKeys('^w')
exit 0
"""
    return _run_hidden_powershell(script)


def close_app_window(target: str) -> bool:
    """Ask a matching app window to close gracefully with Alt+F4; never force-kill it."""
    if os.name != "nt" or not target.strip():
        return False
    normalized = " ".join(target.lower().split())
    normalized = APP_ALIASES.get(normalized, normalized).lower()
    process_names = {
        "brave": "brave",
        "brave browser": "brave",
        "chrome": "chrome",
        "google chrome": "chrome",
        "edge": "msedge",
        "microsoft edge": "msedge",
        "word": "winword",
        "microsoft word": "winword",
        "excel": "excel",
        "microsoft excel": "excel",
        "powerpoint": "powerpnt",
        "outlook": "outlook",
        "notepad": "notepad",
        "spotify": "spotify",
        "code": "code",
        "visual studio code": "code",
        "calculator": "calc",
        "file explorer": "explorer",
        "task manager": "taskmgr",
        "microsoft teams": "ms-teams",
    }
    process_name = process_names.get(normalized, re.sub(r"[^a-z0-9]", "", normalized))
    encoded_process = base64.b64encode(process_name.encode("utf-8")).decode("ascii")
    script = rf"""
$processName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_process}'))
$process = Get-Process -Name $processName -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if (-not $process) {{ exit 2 }}
$shell = New-Object -ComObject WScript.Shell
if (-not $shell.AppActivate([int]$process.Id)) {{ exit 3 }}
Start-Sleep -Milliseconds 150
$shell.SendKeys('%{{F4}}')
exit 0
"""
    return _run_hidden_powershell(script)
