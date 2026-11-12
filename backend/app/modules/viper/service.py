import datetime
import os
import platform
import re
import socket
import subprocess
import urllib.parse
from typing import Any

from sqlalchemy.orm import Session

from app.core.app_launcher import (
    close_active_browser_tab,
    close_app_window,
    launch_desktop_app,
    open_url_with_preferred_browser,
)
from app.core.config import settings
from app.modules.assistant.schemas import ChatMessage, ChatRequest
from app.modules.assistant.service import reply_to_chat
from app.modules.assistant.tools import ToolContext
from app.modules.auth.models import User
from app.modules.viper.schemas import (
    ViperActionDetails,
    ViperCommandResponse,
    ViperTelemetryResponse,
)

NOTES_FILE = os.path.join(os.path.dirname(__file__), "notes.txt")

def transcribe_audio_bytes(wav_bytes: bytes) -> str:
    """Transcribes WAV audio bytes using Groq/OpenAI Whisper if configured, or SpeechRecognition."""
    import io
    if not wav_bytes or len(wav_bytes) < 1000:
        return ""

    # 1. High-accuracy Whisper transcription if API key is present
    if settings.llm_api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
            whisper_model = settings.whisper_model or "whisper-large-v3-turbo"
            transcription = client.audio.transcriptions.create(
                model=whisper_model,
                file=("command.wav", wav_bytes, "audio/wav"),
                language="en",
                response_format="verbose_json",
                temperature=0.0,
            )
            if transcription.text and transcription.text.strip():
                result = transcription.text.strip()
                segments = getattr(transcription, "segments", None) or []
                if segments and all(
                    float(getattr(segment, "no_speech_prob", 0.0) or 0.0) >= 0.65
                    for segment in segments
                ):
                    print("[VIPER Groq Whisper] Ignored a low-speech-confidence transcript.")
                    return ""
                if not re.search(r"[A-Za-z0-9]", result):
                    print("[VIPER Groq Whisper] Ignored a punctuation-only transcript.")
                    return ""
                print(f"[VIPER Groq Whisper] Transcribed: '{result}'")
                return result
        except Exception as e:
            print("[VIPER Whisper] Notice, falling back to Google engine:", e)

    # 2. Multi-accent SpeechRecognition fallback
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        buf = io.BytesIO(wav_bytes)
        with sr.AudioFile(buf) as source:
            audio = recognizer.record(source)

        # Try Indian English first (since user is in India), then standard US/UK
        for lang in ["en-IN", "en-US", "en-GB"]:
            try:
                text = recognizer.recognize_google(audio, language=lang)
                if text and text.strip():
                    return text.strip()
            except sr.UnknownValueError:
                continue
            except Exception as e:
                print(f"[VIPER STT] Error on lang {lang}: {e}")
                break
        return ""
    except Exception as exc:
        print("[VIPER STT] Exception during transcription:", exc)
        return ""


def get_system_telemetry() -> ViperTelemetryResponse:
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

    return ViperTelemetryResponse(
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


def execute_system_action(
    action: str,
    target: str | None = None,
    preferred_browser: str | None = None,
) -> ViperActionDetails:
    action = action.lower().strip()
    target_clean = (target or "").strip()
    browser = preferred_browser or settings.preferred_browser

    try:
        if action == "open_app":
            success, output = launch_desktop_app(target_clean)
            return ViperActionDetails(action=action, target=target_clean, success=success, output=output)

        elif action in ("search_web", "google"):
            query = target_clean or "Google"
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            opened = open_url_with_preferred_browser(url, browser)
            return ViperActionDetails(action="search_web", target=query, success=opened, output=f"Searched Google for: {query}" if opened else "Couldn't open the browser.")

        elif action == "open_url":
            url = target_clean
            if not url.startswith("http://") and not url.startswith("https://"):
                url = f"https://{url}"
            opened = open_url_with_preferred_browser(url, browser)
            return ViperActionDetails(action=action, target=url, success=opened, output=f"Opened {url}" if opened else "Couldn't open the browser.")

        elif action in ("play_music", "youtube"):
            query = target_clean or "relaxing music"
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            opened = open_url_with_preferred_browser(url, browser)
            return ViperActionDetails(action="play_music", target=query, success=opened, output=f"Playing {query} on YouTube" if opened else "Couldn't open the browser.")

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
            return ViperActionDetails(action="volume", target=mode, success=True, output=f"Volume adjusted: {mode}")

        elif action == "lock":
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], timeout=2)
            return ViperActionDetails(action="lock", target="workstation", success=True, output="Workstation locked")

        elif action == "take_note":
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(NOTES_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {target_clean}\n")
            return ViperActionDetails(action="take_note", target=target_clean, success=True, output="Note recorded")

        elif action == "read_notes":
            if os.path.exists(NOTES_FILE):
                with open(NOTES_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                output = "".join(lines[-5:]) if lines else "No notes found."
            else:
                output = "No notes recorded yet, Sir."
            return ViperActionDetails(action="read_notes", target=None, success=True, output=output)

        return ViperActionDetails(action=action, target=target_clean, success=False, output="Unknown action")
    except Exception as exc:
        return ViperActionDetails(action=action, target=target_clean, success=False, output=str(exc))


def _is_contextual_follow_up(text: str) -> bool:
    starts_with_follow_up = re.match(
        r"^(?:and\b|then\b|also\b|now\b|next\b|instead\b|do that\b|do the same\b|"
        r"same for\b|what about\b|how about\b|tell me more\b|continue\b|navigate\b|"
        r"go there\b|show me\b|find me\b|search for\b|open it\b|open that\b|use it\b|"
        r"use that\b|play it\b|play that\b|take me there\b)",
        text,
    )
    compound_action = re.search(
        r"\b(?:and then|then|and)\s+(?:navigate|go|take|show|find|search|open|play|launch|start|use)\b",
        text,
    )
    # Ordinals and references such as "play the first song" need the prior
    # conversation (for example, which service or playlist is currently open).
    contextual_play = re.match(
        r"^(?:please\s+)?(?:play|skip to|choose|select)\s+(?:(?:the|my|that|this)\s+)?"
        r"(?:first|next|last|previous|second|third|fourth|fifth|one|song|track|item)\b",
        text,
    )
    return bool(starts_with_follow_up or compound_action or contextual_play)


def _browser_from_history(history: list[ChatMessage] | None) -> str | None:
    """Carry forward the last positive browser choice for the current task."""
    aliases = (
        ("Google Chrome", r"google\s+chrome"),
        ("Chrome", r"chrome"),
        ("Microsoft Edge", r"microsoft\s+edge"),
        ("Edge", r"edge"),
        ("Brave", r"brave(?:\s+browser)?"),
        ("Firefox", r"(?:mozilla\s+)?firefox"),
        ("Opera GX", r"opera\s+gx"),
        ("Opera", r"opera"),
        ("Vivaldi", r"vivaldi"),
        ("Safari", r"safari"),
    )
    pattern = re.compile("|".join(f"(?P<B{i}>{expr})" for i, (_, expr) in enumerate(aliases)), re.IGNORECASE)
    for message in reversed(history or []):
        if message.role != "user":
            continue
        matches = list(pattern.finditer(message.content))
        positive = []
        for match in matches:
            preceding = message.content[max(0, match.start() - 18):match.start()]
            if re.search(r"\bnot\s+(?:(?:on|in|using|with)\s+)?(?:the\s+)?$", preceding, re.IGNORECASE):
                continue
            group = next((i for i in range(len(aliases)) if match.group(f"B{i}") is not None), None)
            if group is not None:
                positive.append(aliases[group][0])
        if positive:
            return positive[-1]
    return None


def _parse_close_request(message: str) -> tuple[str, str] | None:
    """Return (kind, target) for an explicit close command."""
    cleaned = re.sub(
        r"^(?:(?:hey|ok|okay)\s+)?(?:viper|piper|jarvis)\s*,?\s*",
        "",
        message.strip(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:can|could|would|will)\s+you\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^please\s+", "", cleaned, flags=re.IGNORECASE).strip(" .,!?:;")
    match = re.fullmatch(
        r"(?:close|shut|quit|exit)(?:\s+down)?\s+(?:(?:the|this|that|current|active)\s+)?(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    target = match.group(1).strip(" .,!?:;")
    if re.search(r"\b(?:tab|page)\b", target, re.IGNORECASE):
        return ("tab", target)
    target = re.sub(
        r"\s+(?:that\s+(?:is|was|has\s+been)|that['’]s|which\s+(?:is|was))\s+"
        r"(?:currently\s+)?(?:open(?:ed)?|running|active)\b.*$",
        "",
        target,
        flags=re.IGNORECASE,
    )
    target = re.sub(r"\s+(?:that\s+is\s+)?open(?:ed)?\s+(?:on|in)\s+(?:the\s+)?desktop$", "", target, flags=re.IGNORECASE)
    target = re.sub(r"^(?:the|my)\s+", "", target, flags=re.IGNORECASE)
    target = re.sub(r"^(?:app|application|window)\s+", "", target, flags=re.IGNORECASE)
    target = re.sub(r"\s+(?:desktop\s+)?(?:app|application|window)$", "", target, flags=re.IGNORECASE)
    if target.lower() in {"a", "an", "app", "application", "window", "it", "that"}:
        return None
    return ("app", target)


def _pending_close_request(history: list[ChatMessage] | None) -> tuple[str, str] | None:
    """Find a close request that Viper explicitly asked the user to confirm."""
    turns = history or []
    assistant_index = next(
        (index for index in range(len(turns) - 1, -1, -1) if turns[index].role == "assistant"),
        None,
    )
    if assistant_index is None:
        return None
    assistant_text = turns[assistant_index].content.lower()
    if "close" not in assistant_text or not re.search(
        r"\b(?:confirm|proceed|go ahead|should i|shall i|say yes)\b", assistant_text
    ):
        return None
    for previous in reversed(turns[:assistant_index]):
        if previous.role != "user":
            continue
        return _parse_close_request(previous.content)
    return None


async def _respond_with_conversation(
    cleaned: str,
    user: User,
    db: Session,
    history: list[ChatMessage] | None,
    telemetry: ViperTelemetryResponse,
) -> ViperCommandResponse:
    prompt = (
        "You are Viper, a warm, capable personal assistant. Say your name as the word 'Viper', "
        "never spell out the initials. Understand the latest request using the conversation history, "
        "including references like it, that, there, same, next, and short answers. Continue the current "
        "task when clear. For every open/launch request, classify the target: use open_desktop_app for "
        "installed apps and open_url for websites. For a site, domain, or online service, derive its proper "
        "destination URL from the user's words; keep requested paths or searches in that destination. Treat "
        "'in <browser> Browser' as the browser choice, not part of the target name; an explicitly named "
        "browser overrides the preference. If this is a follow-up in a task with a browser already selected, "
        "keep using that browser unless the user changes it. Use the available "
        "tools to perform requested actions. Speak naturally and concisely, without Markdown or lists. "
        f"Current user turn: {cleaned}"
    )
    try:
        context = ToolContext(user=user, db=db, browser=_browser_from_history(history))
        llm_resp = await reply_to_chat(
            ChatRequest(message=prompt, history=history or []),
            context=context,
        )
        return ViperCommandResponse(
            reply=llm_resp.reply,
            action_taken=f"tools: {', '.join(llm_resp.used_tools)}" if llm_resp.used_tools else None,
            audio_text=llm_resp.reply,
            system_status=telemetry,
        )
    except Exception:
        reply = (
            f"I have received your request: '{cleaned}'. To use conversational AI and follow-up reasoning, "
            "configure LLM_API_KEY in backend/.env."
        )
        return ViperCommandResponse(reply=reply, audio_text=reply, system_status=telemetry)


async def process_viper_command(
    message: str,
    user: User,
    db: Session,
    voice_mode: bool = False,
    history: list[ChatMessage] | None = None,
) -> ViperCommandResponse:
    raw = message.strip()
    # Normalize common typos
    normalized = re.sub(r"\bopne\b", "open", raw, flags=re.IGNORECASE)
    normalized = re.sub(r"\bstrat\b", "start", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\blauch\b", "launch", normalized, flags=re.IGNORECASE)

    # Strip common wake words and pleasantries
    wake_prefix = r"^(?:(?:hey|ok|okay)\s+)?(?:viper|piper|v\s*[.\s]*i\s*[.\s]*p\s*[.\s]*e\s*[.\s]*r|wipe\s+her|jarvis)\s*,?\s*"
    cleaned = re.sub(wake_prefix, "", normalized, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^(?:(?:please|can\s+you(?:\s+please)?|could\s+you(?:\s+please)?|would\s+you(?:\s+please)?|will\s+you(?:\s+please)?)\s*,?\s*)+", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = cleaned.strip(" .,!?:;")
    lower = cleaned.lower()

    telemetry = get_system_telemetry()
    last_assistant_turn = next(
        (item.content.lower() for item in reversed(history or []) if item.role == "assistant"),
        "",
    )

    affirmative = lower in {"yes", "yes please", "yeah", "yep", "sure", "confirm", "go ahead", "do it", "proceed"}
    pending_close = _pending_close_request(history)
    if affirmative and pending_close:
        close_kind, target = pending_close
        if close_kind == "tab":
            browser = _browser_from_history(history) or settings.preferred_browser
            closed = close_active_browser_tab(browser)
            reply = f"Closed the active tab in {browser}." if closed else f"I couldn't find an open {browser} window to close a tab in."
            return ViperCommandResponse(reply=reply, action_taken="CLOSE_TAB", audio_text=reply, system_status=telemetry)
        closed = close_app_window(target)
        reply = f"I sent a normal close request to {target}." if closed else f"I couldn't find an open window for {target}."
        return ViperCommandResponse(reply=reply, action_taken="CLOSE_APP_WINDOW", audio_text=reply, system_status=telemetry)

    if lower == "confirm close tab" and pending_close and pending_close[0] == "tab":
        browser = _browser_from_history(history) or settings.preferred_browser
        closed = close_active_browser_tab(browser)
        reply = f"Closed the active tab in {browser}." if closed else f"I couldn't find an open {browser} window to close a tab in."
        return ViperCommandResponse(reply=reply, action_taken="CLOSE_TAB", audio_text=reply, system_status=telemetry)

    if lower in {"close app", "close application", "close that app", "close this app", "close it"}:
        reply = "Which app should I close? I'll ask you to confirm before closing its window."
        return ViperCommandResponse(reply=reply, action_taken="CLARIFY_CLOSE_APP", audio_text=reply, system_status=telemetry)

    if "which app should i close" in last_assistant_turn and len(cleaned.split()) <= 4:
        app_target = cleaned.strip(" .,!?:;")
        if app_target:
            reply = f"I can ask {app_target} to close its active window. Say 'confirm close app {app_target}' to proceed."
            return ViperCommandResponse(reply=reply, action_taken="CONFIRMATION_REQUIRED", audio_text=reply, system_status=telemetry)

    parsed_close = _parse_close_request(cleaned)
    if parsed_close and parsed_close[0] == "tab":
        browser = _browser_from_history([ChatMessage(role="user", content=cleaned)]) or _browser_from_history(history) or settings.preferred_browser
        reply = f"I can close the active tab in {browser}. Should I close it? Say yes to confirm."
        return ViperCommandResponse(reply=reply, action_taken="CONFIRMATION_REQUIRED", audio_text=reply, system_status=telemetry)

    if parsed_close and parsed_close[0] == "app":
        app_target = parsed_close[1]
        reply = f"I can ask {app_target} to close its active window. Should I close it? Say yes to confirm."
        return ViperCommandResponse(reply=reply, action_taken="CONFIRMATION_REQUIRED", audio_text=reply, system_status=telemetry)

    confirm_app_match = re.fullmatch(r"confirm\s+close\s+app\s+(.+)", cleaned, flags=re.IGNORECASE)
    if confirm_app_match:
        app_target = confirm_app_match.group(1).strip(" .,!?:;")
        if pending_close and pending_close[0] == "app" and pending_close[1].casefold() == app_target.casefold():
            closed = close_app_window(app_target)
            reply = f"I sent a normal close request to {app_target}." if closed else f"I couldn't find an open window for {app_target}."
            return ViperCommandResponse(reply=reply, action_taken="CLOSE_APP_WINDOW", audio_text=reply, system_status=telemetry)

    # Send contextual continuations through the conversation model before simple
    # command patterns can mistake a follow-up for a standalone app name or action.
    if history and _is_contextual_follow_up(lower):
        return await _respond_with_conversation(cleaned, user, db, history, telemetry)

    # Store download / install directive
    store_match = re.search(r"(?:open\s+)?(?:microsoft\s+store|store)\s+(?:and\s+)?(?:download|install|get)\s+(.+)", lower)
    if store_match:
        app_name = store_match.group(1).strip()
        subprocess.Popen(["cmd", "/c", f"start ms-windows-store://search/?query={urllib.parse.quote(app_name)}"], shell=True)
        reply = f"Opening Microsoft Store to download {app_name} for you now, Sir."
        return ViperCommandResponse(
            reply=reply,
            action_taken=f"STORE_DOWNLOAD: {app_name}",
            audio_text=reply,
            system_status=telemetry,
        )

    download_match = re.match(r"^(?:download|install)\s+(.+)$", lower)
    if download_match:
        app_name = download_match.group(1).strip()
        subprocess.Popen(["cmd", "/c", f"start ms-windows-store://search/?query={urllib.parse.quote(app_name)}"], shell=True)
        reply = f"Opening Microsoft Store for {app_name} installation, Sir."
        return ViperCommandResponse(
            reply=reply,
            action_taken=f"STORE_SEARCH: {app_name}",
            audio_text=reply,
            system_status=telemetry,
        )

    # Route every open/launch request through the assistant's generic
    # app-versus-website classifier. Keep this after explicit install requests.
    if re.match(r"^(?:open(?:\s+up)?|launch|start)\s+", lower):
        return await _respond_with_conversation(cleaned, user, db, history, telemetry)

    # Stop / Quiet directive: abort any speech or action immediately
    if lower in ("stop", "shut up", "be quiet", "silence", "quiet", "cancel", "pause", "halt", "abort", "stop talking", "stop listening", "end conversation", "go to standby"):
        return ViperCommandResponse(
            reply="Standing by, Sir.",
            action_taken="STOP_DIRECTIVE",
            audio_text="",
            system_status=telemetry,
        )

    # 0. Wake Word or Greeting alone
    if not cleaned or lower in ("hello", "hi", "hey", "wake up", "are you there", "online", "status"):
        reply = "At your service, Sir. Listening for your command."
        return ViperCommandResponse(
            reply=reply,
            action_taken="WAKE_CONFIRMED",
            audio_text="Yes, Sir?",
            system_status=telemetry,
        )

    if any(k in lower for k in ["good morning", "good evening", "good afternoon"]):
        now_hr = datetime.datetime.now().hour
        period = "morning" if now_hr < 12 else "afternoon" if now_hr < 18 else "evening"
        reply = f"Good {period}, Sir. All systems are online and at your command."
        return ViperCommandResponse(reply=reply, action_taken="GREETING", audio_text=reply, system_status=telemetry)

    # 1. System diagnostics / status / hardware check
    system_check_phrases = [
        "check my system", "check system", "check the system", "how is my system",
        "how's my system", "system status", "system diagnostics", "status report",
        "diagnostics", "check systems", "system specs", "pc status", "hardware status",
        "system info", "laptop specs", "system health"
    ]
    if any(k in lower for k in system_check_phrases):
        reply = (
            f"All systems nominal, Sir. Running {telemetry.os_name} on host '{telemetry.hostname}'. "
            f"Memory utilization is at {telemetry.memory_percent}% ({telemetry.memory_used_gb} GB used of {telemetry.memory_total_gb} GB). "
            f"Power is at {telemetry.battery_percent}% ({telemetry.battery_status}), with CPU operating at nominal levels."
        )
        return ViperCommandResponse(
            reply=reply,
            action_taken="SYSTEM_DIAGNOSTICS",
            audio_text=f"All systems nominal, Sir. Memory is at {telemetry.memory_percent} percent, power is at {telemetry.battery_percent} percent, and operating telemetry is nominal.",
            system_status=telemetry,
        )

    # 2. Time & Date
    if any(k in lower for k in ["what time is it", "current time", "what's the time", "tell me the time"]):
        now_str = datetime.datetime.now().strftime("%I:%M %p")
        reply = f"It is currently {now_str}, Sir."
        return ViperCommandResponse(reply=reply, audio_text=reply, system_status=telemetry)

    if any(k in lower for k in ["what's the date", "what date is it", "today's date", "current date"]):
        date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
        reply = f"Today is {date_str}, Sir."
        return ViperCommandResponse(reply=reply, audio_text=reply, system_status=telemetry)

    # 3. Volume controls
    if "mute" in lower or "unmute" in lower:
        action = execute_system_action("volume", "mute")
        reply = "Audio output muted, Sir." if "unmute" not in lower else "Audio toggled, Sir."
        return ViperCommandResponse(reply=reply, action_taken="volume", action_details=action, audio_text=reply, system_status=telemetry)

    if "volume up" in lower or "increase volume" in lower or "turn it up" in lower:
        action = execute_system_action("volume", "up")
        reply = "Increasing volume, Sir."
        return ViperCommandResponse(reply=reply, action_taken="volume", action_details=action, audio_text=reply, system_status=telemetry)

    if "volume down" in lower or "decrease volume" in lower or "lower volume" in lower:
        action = execute_system_action("volume", "down")
        reply = "Lowering volume, Sir."
        return ViperCommandResponse(reply=reply, action_taken="volume", action_details=action, audio_text=reply, system_status=telemetry)

    # 4. Lock workstation
    if any(k in lower for k in ["lock pc", "lock computer", "lock screen", "lock workstation", "secure pc"]):
        action = execute_system_action("lock")
        reply = "Securing workstation now, Sir."
        return ViperCommandResponse(reply=reply, action_taken="lock", action_details=action, audio_text=reply, system_status=telemetry)

    # 5. Play music / YouTube
    play_match = re.match(r"^(?:play|listen to)\s+(.+?)(?:\s+on\s+youtube)?$", cleaned, flags=re.IGNORECASE)
    if play_match:
        query = play_match.group(1).strip()
        action = execute_system_action("play_music", query)
        reply = f"Searching and playing '{query}' on YouTube, Sir."
        return ViperCommandResponse(reply=reply, action_taken="play_music", action_details=action, audio_text=reply, system_status=telemetry)

    # 6. Web Search
    search_match = re.match(r"^(?:search\s+(?:for\s+)?|google\s+)(.+)$", cleaned, flags=re.IGNORECASE)
    if search_match:
        query = search_match.group(1).strip()
        action = execute_system_action("search_web", query)
        reply = f"Searching Google for '{query}', Sir."
        return ViperCommandResponse(reply=reply, action_taken="search_web", action_details=action, audio_text=reply, system_status=telemetry)

    # 8. Note Taking
    note_match = re.match(r"^(?:take a note|take note|remember that|note down)\s+(.+)$", cleaned, flags=re.IGNORECASE)
    if note_match:
        note_content = note_match.group(1).strip()
        action = execute_system_action("take_note", note_content)
        reply = f"Noted, Sir. I have recorded: '{note_content}'"
        return ViperCommandResponse(reply=reply, action_taken="take_note", action_details=action, audio_text=reply, system_status=telemetry)

    if lower in ("read notes", "show my notes", "what are my notes", "list notes"):
        action = execute_system_action("read_notes")
        reply = f"Here are your latest notes, Sir:\n{action.output}"
        return ViperCommandResponse(reply=reply, action_taken="read_notes", action_details=action, audio_text="Here are your latest notes, Sir.", system_status=telemetry)

    # Conversational intelligence or complex task: delegate to the assistant model.
    return await _respond_with_conversation(cleaned, user, db, history, telemetry)
