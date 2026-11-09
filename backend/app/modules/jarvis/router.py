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
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> JarvisCommandResponse:
    """Accepts raw recorded WAV audio, transcribes it, and executes directive or filters wake word."""
    wav_bytes = await file.read()
    transcribed_text = transcribe_audio_bytes(wav_bytes)
    if not transcribed_text.strip():
        return JarvisCommandResponse(
            reply="I couldn't hear any distinct directive, Sir. Please try speaking again.",
            audio_text="I couldn't hear you clearly, Sir.",
            action_taken="NO_SPEECH_DETECTED",
            system_status=get_system_telemetry(),
        )

    # In wake_mode, check if the transcription contains "jarvis" or common phonetic variants
    if wake_mode:
        lower_text = transcribed_text.lower()
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

    resp = await process_jarvis_command(
        message=transcribed_text,
        user=user,
        db=db,
        voice_mode=True,
    )
    resp.reply = f"[Transcribed: \"{transcribed_text}\"]\n\n{resp.reply}"
    return resp


@router.post("/action", response_model=JarvisActionDetails)
def trigger_action(request: JarvisActionRequest) -> JarvisActionDetails:
    """Directly trigger a system automation action (e.g., open app, volume, lock)."""
    return execute_system_action(request.action, request.target)
