import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.app_index import refresh_installed_app_index, start_app_index_refresh


app = FastAPI(
    title="V.I.P.E.R. API",
    description="Backend API for the V.I.P.E.R. personal assistant.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:8000", "http://localhost:8000", "*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_router, prefix="/api")


@app.on_event("startup")
async def initialize_installed_app_index() -> None:
    # Enumerate Start menu and registry once at startup, then refresh in the
    # background. Individual open commands only consult the in-memory index.
    await asyncio.to_thread(refresh_installed_app_index)
    start_app_index_refresh()

frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
