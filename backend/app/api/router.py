from fastapi import APIRouter

from app.modules.assistant.router import router as assistant_router
from app.modules.auth.router import router as auth_router
from app.modules.autoflow.router import router as autoflow_router
from app.modules.docuvault.router import router as docuvault_router
from app.modules.health.router import router as health_router
from app.modules.inboxzero.router import router as inboxzero_router
from app.modules.viper.router import router as viper_router
from app.modules.learnloop.router import router as learnloop_router
from app.modules.lifeos.router import router as lifeos_router
from app.modules.mealmind.router import router as mealmind_router
from app.modules.pricepilot.router import router as pricepilot_router
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
api_router.include_router(mealmind_router)
api_router.include_router(pricepilot_router)
api_router.include_router(autoflow_router)
api_router.include_router(viper_router, prefix="/viper")
# Keep already-open or older desktop clients working during the V.I.P.E.R. rename.
api_router.include_router(viper_router, prefix="/jarvis", tags=["Legacy V.I.P.E.R. compatibility"])
