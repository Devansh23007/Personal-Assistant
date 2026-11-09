import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.jarvis.schemas import (
    JarvisActionDetails,
    JarvisActionRequest,
    JarvisCommandRequest,
    JarvisCommandResponse,
    JarvisTelemetryResponse,
)
from app.modules.jarvis.service import (
    execute_system_action,
    get_system_telemetry,
    process_jarvis_command,
    transcribe_audio_bytes,
)

router = APIRouter(prefix="/jarvis", tags=["JARVIS Core"])


def _needs_more_speech(text: str) -> bool:
    """Hold obviously incomplete or very short ASR fragments for continuation."""
    normalized = re.sub(r"[^\w\s']", " ", text.lower())
    normalized = re.sub(r"^(?:hey\s+)?jarvis\s*[, ]*", "", normalized).strip()
    words = normalized.split()
    if not words:
        return False

    # These common short utterances are complete standalone commands or replies.
    complete_short = {
        "stop", "cancel", "pause", "mute", "unmute", "hello", "hi", "yes", "no",
        "thanks", "thank you", "good morning", "good evening", "good afternoon",
        "open chrome", "open youtube", "volume up", "volume down", "read notes",
    }
    if normalized in complete_short:
        return False

    # ASR can turn a breath or clipped syllable into a one-word transcript. Don't
    # treat that as a complete request unless it is one of the commands above.
    if len(words) <= 1:
        return True

    unfinished_endings = {
        "a", "an", "the", "of", "to", "for", "with", "and", "or", "but",
        "because", "if", "when", "where", "what", "which", "who", "why", "how",
        "is", "are", "was", "were", "do", "does", "did", "can", "could",
        "would", "should", "me", "about", "my", "your", "their", "its", "what's",
    }
    if words[-1].strip("'") in unfinished_endings:
        return True

    # Catch frequent partial questions whose last word alone is not a function word.
    if re.search(r"\b(?:what(?:'s| is)|tell me)\s+(?:the\s+)?(?:capital|middle|population|weather|distance|meaning)$", normalized):
        return True
    return False


@router.get("/telemetry", response_model=JarvisTelemetryResponse)
def telemetry() -> JarvisTelemetryResponse:
    """Retrieve real-time PC diagnostic metrics (CPU, Memory, Battery, Host info)."""
    return get_system_telemetry()


@router.post("/command", response_model=JarvisCommandResponse)
async def handle_command(
    request: JarvisCommandRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> JarvisCommandResponse:
    """Process a voice or text command for JARVIS, executing system actions or invoking AI tools."""
    return await process_jarvis_command(
        message=request.message,
        user=user,
        db=db,
        voice_mode=request.voice_mode,
    )


@router.post("/voice", response_model=JarvisCommandResponse)
async def handle_voice_upload(
    file: UploadFile = File(...),
    wake_mode: bool = False,
    interrupt_mode: bool = False,
    continuation_text: str = "",
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> JarvisCommandResponse:
    """Accepts raw recorded WAV audio, transcribes it, and executes directive or filters wake word."""
    wav_bytes = await file.read()
    transcribed_text = transcribe_audio_bytes(wav_bytes)
    if interrupt_mode:
        if not transcribed_text.strip():
            return JarvisCommandResponse(reply="", action_taken="NO_STOP_DETECTED", audio_text="")
        normalized = re.sub(r"[^\w\s]", " ", transcribed_text.lower()).strip()
        stop_listening = re.match(
            r"^(?:(?:hey\s+)?jarvis\s+)?(?:please\s+)?(?:stop listening|end conversation|go to standby)$",
            normalized,
        )
        stop_command = re.match(
            r"^(?:(?:hey\s+)?jarvis\s+)?(?:please\s+)?(?:stop(?:\s+talking)?|be\s+quiet|shut\s+up|silence|cancel|pause|halt|abort)$",
            normalized,
        )
        if stop_listening or stop_command:
            return JarvisCommandResponse(
                reply="Stopped.",
                action_taken="STOP_LISTENING" if stop_listening else "STOP_DIRECTIVE",
                audio_text="",
                transcript=transcribed_text.strip(),
            )

        # Ignore tiny fragments that are likely to be echo or recognition noise.
        # A normal interruption should contain a short phrase or question.
        if len(normalized.split()) < 2 and normalized not in {"wait", "actually", "sorry", "hold on"}:
            return JarvisCommandResponse(reply="", action_taken="NO_STOP_DETECTED", audio_text="")

        response = await process_jarvis_command(
            message=transcribed_text.strip(),
            user=user,
            db=db,
            voice_mode=True,
        )
        response.interrupted = True
        response.transcript = transcribed_text.strip()
        response.reply = f"[Transcribed: \"{transcribed_text.strip()}\"]\n\n{response.reply}"
        return response
    if not transcribed_text.strip():
        if continuation_text.strip():
            return JarvisCommandResponse(
                reply="I didn't catch the next part. Please continue.",
                action_taken="CONTINUE_LISTENING",
                audio_text="",
                transcript=continuation_text.strip(),
            )
        return JarvisCommandResponse(
            reply="I couldn't hear any distinct directive, Sir. Please try speaking again.",
            audio_text="I couldn't hear you clearly, Sir.",
            action_taken="NO_SPEECH_DETECTED",
            system_status=get_system_telemetry(),
        )

    combined_text = " ".join(part.strip() for part in (continuation_text, transcribed_text) if part.strip())

    # In wake_mode, check if the transcription contains "jarvis" or common phonetic variants
    if wake_mode:
        lower_text = combined_text.lower()
        cleaned_for_wake = re.sub(r"[^\w\s]", " ", lower_text)
        wake_pattern = r"\b(jarvis|hey\s+jarvis|ok\s+jarvis|okay\s+jarvis|travis|service|harvis|javis|jarv)\b"
        if not re.search(wake_pattern, cleaned_for_wake) and "jarvis" not in cleaned_for_wake:
            # Not directed at Jarvis: ignore quietly so HUD remains in background listening
            return JarvisCommandResponse(
                reply="",
                action_taken="WAKE_IGNORED",
                audio_text="",
                system_status=get_system_telemetry(),
            )

    if _needs_more_speech(combined_text):
        return JarvisCommandResponse(
            reply="Go ahead, I'm listening.",
            action_taken="CONTINUE_LISTENING",
            audio_text="",
            transcript=combined_text,
        )

    resp = await process_jarvis_command(
        message=combined_text,
        user=user,
        db=db,
        voice_mode=True,
    )
    resp.reply = f"[Transcribed: \"{combined_text}\"]\n\n{resp.reply}"
    return resp


@router.post("/action", response_model=JarvisActionDetails)
def trigger_action(request: JarvisActionRequest) -> JarvisActionDetails:
    """Directly trigger a system automation action (e.g., open app, volume, lock)."""
    return execute_system_action(request.action, request.target)
