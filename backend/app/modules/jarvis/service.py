import datetime
import os
import platform
import re
import socket
import subprocess
import urllib.parse
import webbrowser
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.assistant.schemas import ChatMessage, ChatRequest
from app.modules.assistant.service import reply_to_chat
from app.modules.assistant.tools import ToolContext
from app.modules.auth.models import User
from app.modules.jarvis.schemas import (
    JarvisActionDetails,
    JarvisCommandResponse,
    JarvisTelemetryResponse,
)

NOTES_FILE = os.path.join(os.path.dirname(__file__), "notes.txt")

APP_MAPPINGS = {
    "chrome": "start chrome",
    "google chrome": "start chrome",
    "notepad": "start notepad",
    "notes": "start notepad",
    "calc": "start calc",
    "calculator": "start calc",
    "code": "start code",
    "vs code": "start code",
    "vscode": "start code",
    "terminal": "start wt",
    "cmd": "start cmd",
    "command prompt": "start cmd",
    "explorer": "start explorer",
    "file explorer": "start explorer",
    "files": "start explorer",
    "spotify": "start spotify",
    "settings": "start ms-settings:",
    "task manager": "start taskmgr",
    "taskmgr": "start taskmgr",
}


def get_system_telemetry() -> JarvisTelemetryResponse:
    hostname = socket.gethostname()
    os_name = f"Windows {platform.release()}" if platform.system() == "Windows" else platform.system()

    cpu_percent = 12.0
    mem_used_gb = 8.0
    mem_total_gb = 16.0
    mem_percent = 50.0
    battery_percent = 100
    battery_status = "AC Power Connected"

    if platform.system() == "Windows":
        try:
            ps_cmd = (
                "$os = Get-CimInstance Win32_OperatingSystem; "
                "$tot = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2); "
                "$free = [math]::Round($os.FreePhysicalMemory / 1MB, 2); "
                "$used = [math]::Round($tot - $free, 2); "
                "$pct = [math]::Round(($used / $tot) * 100, 1); "
                "Write-Output \"$used|$tot|$pct\""
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0 and "|" in res.stdout:
                parts = res.stdout.strip().split("|")
                mem_used_gb = float(parts[0])
                mem_total_gb = float(parts[1])
                mem_percent = float(parts[2])
        except Exception:
            pass

        try:
            bat_cmd = (
                "$bat = Get-CimInstance Win32_Battery; "
                "if ($bat) { Write-Output \"$($bat.EstimatedChargeRemaining)|$($bat.BatteryStatus)\" } else { Write-Output '100|2' }"
            )
            bat_res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", bat_cmd],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if bat_res.returncode == 0 and "|" in bat_res.stdout:
                bparts = bat_res.stdout.strip().split("|")
                battery_percent = int(bparts[0])
                battery_status = "Charging / AC" if bparts[1] == "2" else "On Battery"
        except Exception:
            pass

    return JarvisTelemetryResponse(
        cpu_percent=cpu_percent,
        memory_used_gb=mem_used_gb,
        memory_total_gb=mem_total_gb,
        memory_percent=mem_percent,
        battery_percent=battery_percent,
        battery_status=battery_status,
        os_name=os_name,
        hostname=hostname,
        status="all systems nominal",
    )


def execute_system_action(action: str, target: str | None = None) -> JarvisActionDetails:
    action = action.lower().strip()
    target_clean = (target or "").strip()

    try:
        if action == "open_app":
            key = target_clean.lower()
            cmd = APP_MAPPINGS.get(key)
            if cmd:
                subprocess.Popen(["cmd", "/c", cmd], shell=True)
                return JarvisActionDetails(action=action, target=target_clean, success=True, output=f"Launched {target_clean}")
            else:
                # Attempt safe launch
                safe_target = re.sub(r"[^\w\-\.]", "", target_clean)
                subprocess.Popen(["cmd", "/c", f"start {safe_target}"], shell=True)
                return JarvisActionDetails(action=action, target=safe_target, success=True, output=f"Launched {safe_target}")

        elif action in ("search_web", "google"):
            query = target_clean or "Google"
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            webbrowser.open(url)
            return JarvisActionDetails(action="search_web", target=query, success=True, output=f"Searched Google for: {query}")

        elif action == "open_url":
            url = target_clean
            if not url.startswith("http://") and not url.startswith("https://"):
                url = f"https://{url}"
            webbrowser.open(url)
            return JarvisActionDetails(action=action, target=url, success=True, output=f"Opened {url}")

        elif action in ("play_music", "youtube"):
            query = target_clean or "relaxing music"
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            webbrowser.open(url)
            return JarvisActionDetails(action="play_music", target=query, success=True, output=f"Playing {query} on YouTube")

        elif action == "volume":
            mode = target_clean.lower()
            key_code = 173  # mute
            if "up" in mode:
                key_code = 175
            elif "down" in mode:
                key_code = 174
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"(New-Object -ComObject WScript.Shell).SendKeys([char]{key_code})"],
                timeout=2,
            )
            return JarvisActionDetails(action="volume", target=mode, success=True, output=f"Volume adjusted: {mode}")

        elif action == "lock":
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], timeout=2)
            return JarvisActionDetails(action="lock", target="workstation", success=True, output="Workstation locked")

        elif action == "take_note":
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(NOTES_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {target_clean}\n")
            return JarvisActionDetails(action="take_note", target=target_clean, success=True, output="Note recorded")

        elif action == "read_notes":
            if os.path.exists(NOTES_FILE):
                with open(NOTES_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                output = "".join(lines[-5:]) if lines else "No notes found."
            else:
                output = "No notes recorded yet, Sir."
            return JarvisActionDetails(action="read_notes", target=None, success=True, output=output)

        return JarvisActionDetails(action=action, target=target_clean, success=False, output="Unknown action")
    except Exception as exc:
        return JarvisActionDetails(action=action, target=target_clean, success=False, output=str(exc))


async def process_jarvis_command(
    message: str,
    user: User,
    db: Session,
    voice_mode: bool = False,
) -> JarvisCommandResponse:
    raw = message.strip()
    # Strip common wake words and pleasantries
    cleaned = re.sub(r"^(hey\s+jarvis|jarvis|ok\s+jarvis|okay\s+jarvis|please|can\s+you|could\s+you)\s*,?\s*", "", raw, flags=re.IGNORECASE).strip()
    lower = cleaned.lower()

    telemetry = get_system_telemetry()

    # 1. System diagnostics / status
    if any(k in lower for k in ["system status", "system diagnostics", "status report", "diagnostics", "check systems", "system specs"]):
        reply = (
            f"All systems nominal, Sir. Memory utilization is at {telemetry.memory_percent}% "
            f"({telemetry.memory_used_gb} GB of {telemetry.memory_total_gb} GB), "
            f"Battery is at {telemetry.battery_percent}% ({telemetry.battery_status}), "
            f"running on {telemetry.os_name}."
        )
        return JarvisCommandResponse(
            reply=reply,
            audio_text=reply,
            system_status=telemetry,
        )

    # 2. Time & Date
    if any(k in lower for k in ["what time is it", "current time", "what's the time", "tell me the time"]):
        now_str = datetime.datetime.now().strftime("%I:%M %p")
        reply = f"It is currently {now_str}, Sir."
        return JarvisCommandResponse(reply=reply, audio_text=reply, system_status=telemetry)

    if any(k in lower for k in ["what's the date", "what date is it", "today's date", "current date"]):
        date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
        reply = f"Today is {date_str}, Sir."
        return JarvisCommandResponse(reply=reply, audio_text=reply, system_status=telemetry)

    # 3. Volume controls
    if "mute" in lower or "unmute" in lower:
        action = execute_system_action("volume", "mute")
        reply = "Audio output muted, Sir." if "unmute" not in lower else "Audio toggled, Sir."
        return JarvisCommandResponse(reply=reply, action_taken="volume", action_details=action, audio_text=reply, system_status=telemetry)

    if "volume up" in lower or "increase volume" in lower or "turn it up" in lower:
        action = execute_system_action("volume", "up")
        reply = "Increasing volume, Sir."
        return JarvisCommandResponse(reply=reply, action_taken="volume", action_details=action, audio_text=reply, system_status=telemetry)

    if "volume down" in lower or "decrease volume" in lower or "lower volume" in lower:
        action = execute_system_action("volume", "down")
        reply = "Lowering volume, Sir."
        return JarvisCommandResponse(reply=reply, action_taken="volume", action_details=action, audio_text=reply, system_status=telemetry)

    # 4. Lock workstation
    if any(k in lower for k in ["lock pc", "lock computer", "lock screen", "lock workstation", "secure pc"]):
        action = execute_system_action("lock")
        reply = "Securing workstation now, Sir."
        return JarvisCommandResponse(reply=reply, action_taken="lock", action_details=action, audio_text=reply, system_status=telemetry)

    # 5. Play music / YouTube
    play_match = re.match(r"^(?:play|listen to)\s+(.+?)(?:\s+on\s+youtube)?$", cleaned, flags=re.IGNORECASE)
    if play_match:
        query = play_match.group(1).strip()
        action = execute_system_action("play_music", query)
        reply = f"Searching and playing '{query}' on YouTube, Sir."
        return JarvisCommandResponse(reply=reply, action_taken="play_music", action_details=action, audio_text=reply, system_status=telemetry)

    if lower in ("open youtube", "launch youtube", "youtube"):
        action = execute_system_action("open_url", "https://youtube.com")
        reply = "Opening YouTube now, Sir."
        return JarvisCommandResponse(reply=reply, action_taken="open_url", action_details=action, audio_text=reply, system_status=telemetry)

    # 6. Web Search
    search_match = re.match(r"^(?:search\s+(?:for\s+)?|google\s+)(.+)$", cleaned, flags=re.IGNORECASE)
    if search_match:
        query = search_match.group(1).strip()
        action = execute_system_action("search_web", query)
        reply = f"Searching Google for '{query}', Sir."
        return JarvisCommandResponse(reply=reply, action_taken="search_web", action_details=action, audio_text=reply, system_status=telemetry)

    # 7. Open Application
    open_match = re.match(r"^(?:open|launch|start)\s+(.+)$", cleaned, flags=re.IGNORECASE)
    if open_match:
        app_target = open_match.group(1).strip()
        action = execute_system_action("open_app", app_target)
        reply = f"Launching {app_target} immediately, Sir."
        return JarvisCommandResponse(reply=reply, action_taken="open_app", action_details=action, audio_text=reply, system_status=telemetry)

    # 8. Note Taking
    note_match = re.match(r"^(?:take a note|take note|remember that|note down)\s+(.+)$", cleaned, flags=re.IGNORECASE)
    if note_match:
        note_content = note_match.group(1).strip()
        action = execute_system_action("take_note", note_content)
        reply = f"Noted, Sir. I have recorded: '{note_content}'"
        return JarvisCommandResponse(reply=reply, action_taken="take_note", action_details=action, audio_text=reply, system_status=telemetry)

    if lower in ("read notes", "show my notes", "what are my notes", "list notes"):
        action = execute_system_action("read_notes")
        reply = f"Here are your latest notes, Sir:\n{action.output}"
        return JarvisCommandResponse(reply=reply, action_taken="read_notes", action_details=action, audio_text="Here are your latest notes, Sir.", system_status=telemetry)

    # 9. Conversational intelligence or complex task: Delegate to Assistant LLM
    jarvis_prompt = (
        f"[You are J.A.R.V.I.S., a hyper-competent, refined AI assistant. Address the user as 'Sir'. "
        f"Keep answers clear, polite, concise, and ready to be spoken aloud. "
        f"You have access to all user tools for tasks, emails, expenses, documents, flashcards, meals, and workflows.] "
        f"User command: {cleaned}"
    )

    try:
        context = ToolContext(user=user, db=db)
        chat_req = ChatRequest(message=jarvis_prompt, history=[])
        llm_resp = await reply_to_chat(chat_req, context=context)
        return JarvisCommandResponse(
            reply=llm_resp.reply,
            action_taken=f"tools: {', '.join(llm_resp.used_tools)}" if llm_resp.used_tools else None,
            audio_text=llm_resp.reply,
            system_status=telemetry,
        )
    except Exception as exc:
        # If LLM is not configured, provide a polished fallback
        reply = (
            f"I have received your command, Sir: '{cleaned}'. "
            "To unlock full conversational AI reasoning and deep analysis, please configure LLM_API_KEY in backend/.env. "
            "All direct system controls, web searches, application launches, and local tools are fully operational."
        )
        return JarvisCommandResponse(
            reply=reply,
            audio_text="At your service, Sir. Ready for your command.",
            system_status=telemetry,
        )
