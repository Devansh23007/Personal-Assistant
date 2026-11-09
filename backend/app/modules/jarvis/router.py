from typing import Annotated

from fastapi import APIRouter, Depends
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


@router.post("/action", response_model=JarvisActionDetails)
def trigger_action(request: JarvisActionRequest) -> JarvisActionDetails:
    """Directly trigger a system automation action (e.g., open app, volume, lock)."""
    return execute_system_action(request.action, request.target)
