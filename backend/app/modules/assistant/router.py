from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.assistant.schemas import ChatRequest, ChatResponse
from app.modules.assistant.service import reply_to_chat
from app.modules.assistant.tools import ToolContext
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ChatResponse:
    context = ToolContext(user=current_user, db=db)
    return await reply_to_chat(payload, context=context)
