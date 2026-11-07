from fastapi import APIRouter

from app.modules.assistant.router import router as assistant_router
from app.modules.auth.router import router as auth_router
from app.modules.docuvault.router import router as docuvault_router
from app.modules.health.router import router as health_router
from app.modules.inboxzero.router import router as inboxzero_router
from app.modules.learnloop.router import router as learnloop_router
from app.modules.lifeos.router import router as lifeos_router
from app.modules.spendwise.router import router as spendwise_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(assistant_router)
api_router.include_router(lifeos_router)
api_router.include_router(inboxzero_router)
api_router.include_router(spendwise_router)
api_router.include_router(docuvault_router)
api_router.include_router(learnloop_router)
