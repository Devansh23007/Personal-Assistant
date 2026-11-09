from typing import Any
from pydantic import BaseModel, Field
from app.modules.assistant.schemas import ChatMessage


class JarvisCommandRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    voice_mode: bool = False
    client_time: str | None = None
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class JarvisActionDetails(BaseModel):
    action: str
    target: str | None = None
    success: bool = True
    output: str | None = None


class JarvisTelemetryResponse(BaseModel):
    cpu_percent: float | None = None
    memory_used_gb: float | None = None
    memory_total_gb: float | None = None
    memory_percent: float | None = None
    battery_percent: int | None = None
    battery_status: str | None = None
    os_name: str
    hostname: str
    status: str = "nominal"


class JarvisCommandResponse(BaseModel):
    reply: str
    action_taken: str | None = None
    action_details: JarvisActionDetails | None = None
    system_status: JarvisTelemetryResponse | None = None
    audio_text: str | None = None
    transcript: str | None = None
    interrupted: bool = False


class JarvisActionRequest(BaseModel):
    action: str = Field(..., description="Action name, e.g. open_app, search_web, volume, lock")
    target: str | None = None


class SpeechRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    voice: str = Field(default="troy", pattern="^(autumn|diana|hannah|austin|daniel|troy)$")
