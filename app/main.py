"""Punto de entrada FastAPI. Fase 0/1: arranque + índices + healthcheck.

Los routers (/import, /agent, /auth, /playlists) se irán montando en fases
posteriores.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.agent.router import router as agent_router
from app.db.client import close_client, get_db
from app.db.indexes import ensure_indexes
from app.dj import router as dj_router
from app.drafts import router as drafts_router
from app.ingest.router import router as ingest_router
from app.prefs_router import router as prefs_router
from app.scheduler import build_scheduler
from app.spotify.router import router as auth_router
from app.suggest_router import router as suggest_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes(get_db())
    scheduler = build_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown(wait=False)
    await close_client()


app = FastAPI(title="VibeSync — AI Playlist Generator", lifespan=lifespan)
app.include_router(ingest_router)
app.include_router(agent_router)
app.include_router(auth_router)
app.include_router(dj_router)
app.include_router(drafts_router)
app.include_router(prefs_router)
app.include_router(suggest_router)

_WEB = Path(__file__).parent / "web" / "index.html"


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(str(_WEB))


@app.get("/health")
async def health():
    db = get_db()
    await db.command("ping")
    return {"status": "ok", "db": db.name}
