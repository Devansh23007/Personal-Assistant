from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health() -> dict[str, str]:
    return {
        "status": "ok",
        "database": "configured",
        "assistant": "configured" if settings.llm_api_key and settings.llm_model else "not_configured",
    }


@router.get("/ready")
def get_readiness() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready"}
