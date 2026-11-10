import asyncio
import io
import json
import re
import urllib.error
import urllib.request
import wave
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.assistant.schemas import ChatMessage
from app.modules.viper.schemas import (
    ViperActionDetails,
    ViperActionRequest,
    ViperCommandRequest,
    ViperCommandResponse,
    ViperTelemetryResponse,
    SpeechRequest,
)
from app.modules.viper.service import (
    execute_system_action,
    get_system_telemetry,
    process_viper_command,
    transcribe_audio_bytes,
)

router = APIRouter(tags=["VIPER Core"])


def _needs_more_speech(text: str, history: list[ChatMessage] | None = None) -> bool:
    """Hold obviously incomplete or very short ASR fragments for continuation."""
    normalized = re.sub(r"[^\w\s']", " ", text.lower())
    normalized = re.sub(r"^(?:hey\s+)?viper\s*[, ]*", "", normalized).strip()
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
        # A one-word reply is complete when the assistant just asked a clarification
        # question (for example, the user answering "Brave" to "Which browser?").
        last_assistant = next(
            (message.content for message in reversed(history or []) if message.role == "assistant"),
            "",
        )
        is_answer_to_clarification = (
            "?" in last_assistant
            and re.search(
                r"\b(which|what|who|where|when|how|specify|clarify)\b",
                last_assistant,
                flags=re.IGNORECASE,
            ) is not None
        )
        return not is_answer_to_clarification

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


def _is_assistant_echo(text: str, history: list[ChatMessage]) -> bool:
    """Ignore likely speaker-to-microphone echo during barge-in transcription."""
    words = re.findall(r"[a-z0-9']+", text.lower())
    if len(words) < 2:
        return False
    last_assistant = next(
        (message.content for message in reversed(history) if message.role == "assistant"),
        "",
    )
    assistant_words = re.findall(r"[a-z0-9']+", last_assistant.lower())
    if not assistant_words or len(words) > len(assistant_words):
        return False
    spoken_phrase = " ".join(words)
    assistant_text = " ".join(assistant_words)
    return f" {spoken_phrase} " in f" {assistant_text} "


def _is_repeated_gratitude(text: str, history: list[ChatMessage]) -> bool:
    normalized = " ".join(re.findall(r"[a-z']+", text.lower()))
    if normalized not in {"thank you", "thanks", "thanks viper", "thank you viper"}:
        return False
    last_assistant = next(
        (message.content.lower() for message in reversed(history) if message.role == "assistant"),
        "",
    )
    return "welcome" in last_assistant


def _parse_history(raw_history: str) -> list[ChatMessage]:
    try:
        values = json.loads(raw_history)
        if not isinstance(values, list):
            return []
        return [ChatMessage.model_validate(item) for item in values[-20:]]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _split_tts_text(text: str, max_chars: int = 190) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        remaining = sentence.strip()
        while len(remaining) > max_chars:
            split_at = remaining.rfind(" ", 0, max_chars + 1)
            if split_at <= 0:
                split_at = max_chars
            piece, remaining = remaining[:split_at].strip(), remaining[split_at:].strip()
            if current:
                chunks.append(current)
                current = ""
            if piece:
                chunks.append(piece)
        if not remaining:
            continue
        candidate = f"{current} {remaining}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = remaining
    if current:
        chunks.append(current)
    return chunks


def _request_groq_speech(text: str, voice: str) -> bytes:
    api_key = settings.tts_api_key or settings.llm_api_key
    if not api_key:
        raise RuntimeError("TTS API key is not configured")
    payload = json.dumps({
        "model": settings.tts_model,
        "input": text,
        "voice": voice,
        "response_format": "wav",
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{settings.tts_base_url.rstrip('/')}/audio/speech",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "audio/wav",
            "User-Agent": "ViperDesktopAssistant/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def _join_wav_audio(parts: list[bytes]) -> bytes:
    audio_params: tuple[int, int, int, str, str] | None = None
    frames: list[bytes] = []
    for part in parts:
        with wave.open(io.BytesIO(part), "rb") as reader:
            current_params = (
                reader.getnchannels(),
                reader.getsampwidth(),
                reader.getframerate(),
                reader.getcomptype(),
                reader.getcompname(),
            )
            if audio_params is not None and current_params != audio_params:
                raise ValueError("Speech chunks have incompatible WAV formats")
            audio_params = current_params
            frames.append(reader.readframes(reader.getnframes()))
    if audio_params is None:
        raise ValueError("Speech provider returned no audio")

    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(audio_params[0])
        writer.setsampwidth(audio_params[1])
        writer.setframerate(audio_params[2])
        writer.setcomptype(audio_params[3], audio_params[4])
        writer.writeframes(b"".join(frames))
    return output.getvalue()


@router.get("/telemetry", response_model=ViperTelemetryResponse)
def telemetry() -> ViperTelemetryResponse:
    """Retrieve real-time PC diagnostic metrics (CPU, Memory, Battery, Host info)."""
    return get_system_telemetry()


@router.post("/command", response_model=ViperCommandResponse)
async def handle_command(
    request: ViperCommandRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ViperCommandResponse:
    """Process a voice or text command for VIPER, executing system actions or invoking AI tools."""
    return await process_viper_command(
        message=request.message,
        user=user,
        db=db,
        voice_mode=request.voice_mode,
        history=request.history,
    )


@router.post("/voice", response_model=ViperCommandResponse)
async def handle_voice_upload(
    request: Request,
    file: UploadFile = File(...),
    wake_mode: bool = False,
    interrupt_mode: bool = False,
    continuation_text: str = "",
    history_json: str = Form(default="[]"),
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ViperCommandResponse:
    """Accepts raw recorded WAV audio, transcribes it, and executes directive or filters wake word."""
    wav_bytes = await file.read()
    transcribed_text = transcribe_audio_bytes(wav_bytes)
    history = _parse_history(history_json)
    if interrupt_mode:
        if not transcribed_text.strip():
            return ViperCommandResponse(reply="", action_taken="NO_STOP_DETECTED", audio_text="")
        normalized = re.sub(r"[^\w\s]", " ", transcribed_text.lower()).strip()
        stop_listening = re.match(
            r"^(?:(?:hey\s+)?viper\s+)?(?:please\s+)?(?:stop listening|end conversation|go to standby)$",
            normalized,
        )
        stop_command = re.match(
            r"^(?:(?:hey\s+)?viper\s+)?(?:please\s+)?(?:stop(?:\s+talking)?|be\s+quiet|shut\s+up|silence|cancel|pause|halt|abort)$",
            normalized,
        )
        if stop_listening or stop_command:
            return ViperCommandResponse(
                reply="Stopped.",
                action_taken="STOP_LISTENING" if stop_listening else "STOP_DIRECTIVE",
                audio_text="",
                transcript=transcribed_text.strip(),
            )

        if _is_assistant_echo(transcribed_text, history):
            return ViperCommandResponse(reply="", action_taken="NO_STOP_DETECTED", audio_text="")

        # Ignore tiny fragments that are likely to be echo or recognition noise.
        # A normal interruption should contain a short phrase or question.
        if len(normalized.split()) < 2 and normalized not in {"wait", "actually", "sorry", "hold on"}:
            return ViperCommandResponse(reply="", action_taken="NO_STOP_DETECTED", audio_text="")

        response = await process_viper_command(
            message=transcribed_text.strip(),
            user=user,
            db=db,
            voice_mode=True,
            history=history,
        )
        response.interrupted = True
        response.transcript = transcribed_text.strip()
        response.reply = f"[Transcribed: \"{transcribed_text.strip()}\"]\n\n{response.reply}"
        return response
    if not transcribed_text.strip():
        if continuation_text.strip():
            return ViperCommandResponse(
                reply="I didn't catch the next part. Please continue.",
                action_taken="CONTINUE_LISTENING",
                audio_text="",
                transcript=continuation_text.strip(),
            )
        return ViperCommandResponse(
            reply="I couldn't hear any distinct directive, Sir. Please try speaking again.",
            audio_text="I couldn't hear you clearly, Sir.",
            action_taken="NO_SPEECH_DETECTED",
            system_status=get_system_telemetry(),
        )

    combined_text = " ".join(part.strip() for part in (continuation_text, transcribed_text) if part.strip())

    if _is_repeated_gratitude(combined_text, history):
        return ViperCommandResponse(reply="", action_taken="ECHO_IGNORED", audio_text="")

    # In wake_mode, check if the transcription contains "viper" or common phonetic variants
    if wake_mode:
        lower_text = combined_text.lower()
        cleaned_for_wake = re.sub(r"[^\w\s]", " ", lower_text)
        # ASR may render the acronym as "V.I.P.E.R." or "V I P E R".
        cleaned_for_wake = re.sub(r"\bv\s+i\s+p\s+e\s+r\b", "viper", cleaned_for_wake)
        # A still-open legacy client can call the old API path and old wake phrase.
        if request.url.path.startswith("/api/jarvis/"):
            cleaned_for_wake = re.sub(r"\b(?:hey\s+)?jarvis\b", "viper", cleaned_for_wake)
        wake_pattern = r"\b(viper|hey\s+viper|ok\s+viper|okay\s+viper|piper|wiper|wipe\s+her)\b"
        if not re.search(wake_pattern, cleaned_for_wake):
            # Not directed at V.I.P.E.R.: ignore quietly so HUD remains in background listening
            return ViperCommandResponse(
                reply="",
                action_taken="WAKE_IGNORED",
                audio_text="",
                system_status=get_system_telemetry(),
            )

    if _needs_more_speech(combined_text, history):
        return ViperCommandResponse(
            reply="Go ahead, I'm listening.",
            action_taken="CONTINUE_LISTENING",
            audio_text="",
            transcript=combined_text,
        )

    resp = await process_viper_command(
        message=combined_text,
        user=user,
        db=db,
        voice_mode=True,
        history=history,
    )
    resp.transcript = combined_text
    resp.reply = f"[Transcribed: \"{combined_text}\"]\n\n{resp.reply}"
    return resp


@router.post("/speech", response_class=Response)
async def synthesize_speech(request: SpeechRequest) -> Response:
    """Generate natural English speech without exposing the provider key to the browser."""
    if not (settings.tts_api_key or settings.llm_api_key):
        raise HTTPException(status_code=503, detail="Natural speech is not configured.")
    chunks = _split_tts_text(request.text)
    try:
        audio_parts = [
            await asyncio.to_thread(_request_groq_speech, chunk, request.voice)
            for chunk in chunks
        ]
        audio = _join_wav_audio(audio_parts)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, ValueError, wave.Error) as exc:
        if isinstance(exc, urllib.error.HTTPError):
            provider_error = exc.read().decode("utf-8", errors="replace")[:1000]
            if "model_terms_required" in provider_error:
                print("[VIPER TTS] Orpheus terms have not been accepted for this Groq organization.")
                raise HTTPException(
                    status_code=503,
                    detail="Accept the Orpheus model terms in Groq Console to enable natural speech.",
                ) from exc
            print(f"[VIPER TTS] Provider returned HTTP {exc.code}: {provider_error}")
        else:
            print(f"[VIPER TTS] Speech generation failed: {exc}")
        raise HTTPException(status_code=502, detail="Natural speech generation is unavailable.") from exc
    return Response(content=audio, media_type="audio/wav")


@router.post("/action", response_model=ViperActionDetails)
def trigger_action(request: ViperActionRequest) -> ViperActionDetails:
    """Directly trigger a system automation action (e.g., open app, volume, lock)."""
    return execute_system_action(request.action, request.target)
