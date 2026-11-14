"""Safe desktop app launching shared by V.I.P.E.R. and assistant tools."""

import base64
import os
import re
import shutil
import subprocess
import sys


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

_opened_processes: dict[str, int] = {}


def _record_open_process(target: str, process: subprocess.Popen[bytes] | subprocess.Popen[str]) -> None:
    normalized = " ".join(target.lower().split())
    canonical = APP_ALIASES.get(normalized, normalized)
    if process.pid:
        _opened_processes[normalized] = process.pid
        _opened_processes[" ".join(canonical.lower().split())] = process.pid


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
            process = subprocess.Popen(command, shell=False)
            _record_open_process(name, process)
            return True, f"Opened {name}."
        except OSError:
            # Some Windows apps are installed as packaged apps and only appear
            # in the Start menu registry, so try the registered app lookup below.
            pass

    app_name = APP_ALIASES.get(normalized, name)
    from app.core.app_index import find_installed_app
    installed = find_installed_app(app_name, APP_ALIASES)
    if installed:
        try:
            if installed.app_id and os.name == "nt":
                process = subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{installed.app_id}"], shell=False)
            elif installed.shortcut and os.name == "nt":
                os.startfile(installed.shortcut)  # type: ignore[attr-defined]
                process = None
            elif installed.executable:
                process = subprocess.Popen([installed.executable], shell=False)
            else:
                executable = shutil.which(normalized)
                if executable:
                    process = subprocess.Popen([executable], shell=False)
                elif installed.app_id and os.name == "nt":
                    process = subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{installed.app_id}"], shell=False)
                else:
                    return False, f"'{installed.name}' is indexed, but its launch target is unavailable."
            if process is not None and not installed.app_id:
                _record_open_process(name, process)
            return True, f"Opened {installed.name}."
        except OSError as exc:
            return False, f"Couldn't open {installed.name}: {exc}"
    if os.name == "nt":
        return False, f"I couldn't find an installed app matching '{name}'."

    executable = shutil.which(normalized)
    if executable:
        try:
            process = subprocess.Popen([executable], shell=False)
            _record_open_process(name, process)
            return True, f"Opened {name}."
        except OSError as exc:
            return False, f"Couldn't open {name}: {exc}"
    return False, f"I couldn't find an installed app named '{name}' on {sys.platform}."


def open_url_with_preferred_browser(url: str, preferred_browser: str = "Brave") -> bool:
    """Open a URL in the requested browser, falling back to the OS default."""
    browser = preferred_browser.strip().lower()
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    browser_candidates = {
        "brave": [
            shutil.which("brave.exe"), shutil.which("brave"),
            os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(program_files_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ],
        "brave browser": [
            shutil.which("brave.exe"),
            os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ],
        "chrome": [
            shutil.which("chrome.exe"), shutil.which("chrome"),
            os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
        ],
        "google chrome": [
            shutil.which("chrome.exe"),
            os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
        ],
        "edge": [
            shutil.which("msedge.exe"), shutil.which("msedge"),
            os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
        ],
        "microsoft edge": [
            shutil.which("msedge.exe"),
            os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
        ],
    }
    # Support browsers beyond the common bundled choices when their command is
    # on PATH (for example Firefox, Vivaldi, Opera, or a user-installed one).
    command_name = re.sub(r"\s+browser$", "", browser).strip()
    generic_candidates = [
        shutil.which(command_name),
        shutil.which(command_name.replace(" ", "")),
        shutil.which(command_name.replace(" ", "") + ".exe"),
    ]
    candidates = [*browser_candidates.get(browser, []), *generic_candidates]
    executable = next((candidate for candidate in candidates if candidate and os.path.isfile(candidate)), None)
    if executable:
        try:
            subprocess.Popen([executable, url], shell=False)
            return True
        except OSError:
            pass
    # Don't silently open in a different browser than the one requested.
    return False


def _execute_hidden_powershell(script: str) -> tuple[int | None, str]:
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded_script],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        return result.returncode, (result.stderr or result.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return None, "PowerShell timed out after 8 seconds."
    except OSError as exc:
        return -1, str(exc)


def _run_hidden_powershell(script: str) -> bool:
    return _execute_hidden_powershell(script)[0] == 0


def navigate_current_browser_tab(url: str, preferred_browser: str = "Brave") -> bool:
    """Navigate the active tab in the preferred browser without opening a new tab."""
    if os.name != "nt" or not preferred_browser.strip():
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


def close_active_browser_tab_status(preferred_browser: str = "Brave") -> tuple[bool, str]:
    """Close the active tab in the requested browser with a normal Ctrl+W request."""
    if os.name != "nt" or not preferred_browser.strip():
        return False, "Tab close is only available on Windows, or no browser was selected."
    browser = " ".join(preferred_browser.strip().lower().split())
    window_name = {
        "google chrome": "Chrome",
        "chrome": "Chrome",
        "microsoft edge": "Edge",
        "edge": "Edge",
        "brave browser": "Brave",
        "brave": "Brave",
        "mozilla firefox": "Firefox",
        "firefox": "Firefox",
        "opera gx": "Opera GX",
        "opera": "Opera",
        "vivaldi": "Vivaldi",
        "safari": "Safari",
    }.get(browser, preferred_browser.strip())
    encoded_browser = base64.b64encode(window_name.encode("utf-8")).decode("ascii")
    script = rf"""
$browser = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_browser}'))
$shell = New-Object -ComObject WScript.Shell
if (-not $shell.AppActivate($browser)) {{ exit 2 }}
Start-Sleep -Milliseconds 150
$shell.SendKeys('^w')
exit 0
"""
    code, detail = _execute_hidden_powershell(script)
    if code == 0:
        return True, f"Windows sent Ctrl+W to the active {window_name} window."
    if code == 2:
        return False, f"No active {window_name} window accepted the tab-close request. (PowerShell exit code 2)"
    if code is None:
        return False, detail
    return False, f"Tab close failed with PowerShell exit code {code}. {detail}".strip()


def close_active_browser_tab(preferred_browser: str = "Brave") -> bool:
    return close_active_browser_tab_status(preferred_browser)[0]


def close_app_window_status(target: str, all_windows: bool = False, force: bool = False) -> tuple[bool, str]:
    """Request a graceful app-managed close for a matching desktop window."""
    if os.name != "nt" or not target.strip():
        return False, "Desktop window close is only available on Windows, or the target was empty."
    normalized = " ".join(target.lower().split())
    app_name = APP_ALIASES.get(normalized, target.strip())
    command = COMMAND_ALIASES.get(normalized)
    process_hint = os.path.splitext(os.path.basename(command[0]))[0] if command else app_name
    process_hint = {
        "word": "WINWORD", "microsoft word": "WINWORD", "visual studio code": "Code",
        "vs code": "Code", "vscode": "Code", "microsoft store": "WinStore.App",
        "google chrome": "chrome", "brave browser": "brave", "microsoft edge": "msedge",
    }.get(normalized, process_hint)
    encoded_app = base64.b64encode(app_name.encode("utf-8")).decode("ascii")
    encoded_process = base64.b64encode(process_hint.encode("utf-8")).decode("ascii")
    tracked_pid = _opened_processes.get(normalized, 0)
    if force:
        process_name = {"chrome": "chrome", "google chrome": "chrome", "brave": "brave", "brave browser": "brave", "edge": "msedge", "microsoft edge": "msedge"}.get(normalized, process_hint)
        encoded_name = base64.b64encode(process_name.encode("utf-8")).decode("ascii")
        tracked_pid = _opened_processes.get(normalized, 0)
        script = rf"""
$name = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_name}'))
$procs = @()
if ({tracked_pid} -gt 0) {{ $tracked = Get-Process -Id {tracked_pid} -ErrorAction SilentlyContinue; if ($tracked) {{ $procs += $tracked }} }}
if ($procs.Count -eq 0) {{
  $procs = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {{ $_.ProcessName -ieq $name -or ($_.MainWindowTitle -and $_.MainWindowTitle.IndexOf($name, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) }})
}}
if ($procs.Count -eq 0) {{ exit 2 }}
$ids = @($procs | ForEach-Object {{ $_.Id }})
Stop-Process -Id $ids -Force -ErrorAction Stop
exit 0
"""
        code, detail = _execute_hidden_powershell(script)
        if code == 0:
            return True, f"Force-closed {process_name} after confirmation."
        if code == 2:
            return False, f"No running {process_name} process was found. (PowerShell exit code 2)"
        if code is None:
            return False, detail
        return False, f"Force close failed with PowerShell exit code {code}. {detail}".strip()
    if all_windows:
        process_name = {"chrome": "chrome", "google chrome": "chrome", "brave": "brave", "brave browser": "brave", "edge": "msedge", "microsoft edge": "msedge", "firefox": "firefox"}.get(normalized, process_hint)
        encoded_name = base64.b64encode(process_name.encode("utf-8")).decode("ascii")
        script = rf"""
$name = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_name}'))
$procs = @(Get-Process -Name $name -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }})
if ($procs.Count -eq 0) {{ exit 2 }}
$accepted = 0
foreach ($proc in $procs) {{ if ($proc.CloseMainWindow()) {{ $accepted++ }} }}
if ($accepted -eq 0) {{ exit 4 }}
exit 0
"""
        code, detail = _execute_hidden_powershell(script)
        if code == 0:
            return True, f"Windows accepted close requests for {process_name} windows."
        if code == 2:
            return False, f"No visible {process_name} windows are running. (PowerShell exit code 2)"
        if code is None:
            return False, detail
        return False, f"Windows did not accept a graceful close request. (PowerShell exit code {code}) {detail}".strip()

    script = rf"""
$appName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_app}'))
$processHint = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_process}'))
$source = @'
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;

public static class ViperDesktopWindowMatcher {{
    private delegate bool EnumWindowsCallback(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsCallback callback, IntPtr lParam);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint message, IntPtr wParam, IntPtr lParam);

    private static string Normalize(string value) {{
        return Regex.Replace((value ?? "").ToLowerInvariant(), "[^a-z0-9]", "");
    }}

    public static IntPtr FindWindow(string appName, string processHint, int trackedPid) {{
        string normalizedApp = Normalize(appName);
        string normalizedProcess = Normalize(processHint);
        IntPtr match = IntPtr.Zero;
        int bestScore = 0;
        var appTokens = Regex.Matches(appName ?? "", "[A-Za-z0-9]+");
        string lastAppWord = appTokens.Count > 0 ? Normalize(appTokens[appTokens.Count - 1].Value) : normalizedApp;
        EnumWindows((hWnd, lParam) => {{
            if (!IsWindowVisible(hWnd)) return true;
            var titleBuffer = new StringBuilder(1024);
            GetWindowText(hWnd, titleBuffer, titleBuffer.Capacity);
            string rawTitle = titleBuffer.ToString();
            string title = Normalize(rawTitle);
            uint processId;
            GetWindowThreadProcessId(hWnd, out processId);
            string processName = "";
            try {{ processName = Normalize(Process.GetProcessById((int)processId).ProcessName); }} catch {{ }}

            int score = 0;
            if (trackedPid > 0 && processId == (uint)trackedPid) {{
                score = 5;
            }} else if ((normalizedApp.Length > 0 && processName == normalizedApp) ||
                (normalizedProcess.Length > 0 && processName == normalizedProcess)) {{
                score = 4;
            }} else if (lastAppWord.Length >= 4 && processName.Contains(lastAppWord)) {{
                score = 3;
            }} else if (normalizedApp.Length > 0 && title.Contains(normalizedApp)) {{
                score = 2;
            }} else if (lastAppWord.Length >= 4 &&
                Regex.IsMatch(rawTitle, @"(?:^|[^A-Za-z0-9])" + Regex.Escape(lastAppWord) + @"(?:$|[^A-Za-z0-9])", RegexOptions.IgnoreCase)) {{
                score = 1;
            }}
            if (score > bestScore) {{
                bestScore = score;
                match = hWnd;
                if (score == 4) return false;
            }}
            return true;
        }}, IntPtr.Zero);
        return match;
    }}
}}
'@
try {{ Add-Type -TypeDefinition $source -ErrorAction Stop }} catch {{ exit 3 }}
$window = [ViperDesktopWindowMatcher]::FindWindow($appName, $processHint, {tracked_pid})
if ($window -eq [IntPtr]::Zero) {{ exit 2 }}
# WM_CLOSE requests an ordinary, app-managed close (including unsaved-work prompts).
if ([ViperDesktopWindowMatcher]::PostMessage($window, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)) {{ exit 0 }}
exit 4
"""
    code, detail = _execute_hidden_powershell(script)
    if code == 0:
        return True, f"Windows accepted the close request for {target}."
    if code == 2:
        return False, f"No visible window matched {target}. (PowerShell exit code 2)"
    if code == 3:
        return False, f"Could not initialize the window matcher. (PowerShell exit code 3) {detail}".strip()
    if code == 4:
        return False, f"Windows rejected the close request for {target}. (PowerShell exit code 4)"
    if code is None:
        return False, detail
    return False, f"Window close failed with PowerShell exit code {code}. {detail}".strip()


def close_app_window(target: str, all_windows: bool = False) -> bool:
    return close_app_window_status(target, all_windows=all_windows)[0]
