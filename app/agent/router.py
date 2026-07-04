"""Endpoint del agente DJ (DeepSeek + tool loop)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.executors import build_executors
from app.agent.llm import DeepSeekClient
from app.agent.runner import run_agent
from app.agent.tools import ARG_MODELS, TOOL_SCHEMAS
from app.config import get_settings
from app.db.client import get_db
from app.enrich.embeddings import get_embedder
from app.enrich.lastfm import LastFmClient
from app.spotify.playlists import SpotifyPlaylistController

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    user_id: str
    message: str
    access_token: str | None = None   # token de Spotify para poder escribir playlists


@router.post("/chat")
async def chat(req: AgentRequest):
    s = get_settings()
    if not s.deepseek_api_key:
        raise HTTPException(400, "DEEPSEEK_API_KEY no configurada")
    db = get_db()
    llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
    lastfm = LastFmClient(s.lastfm_api_key) if s.lastfm_api_key else None
    spotify = SpotifyPlaylistController(req.access_token, db=db) if req.access_token else None
    executors = build_executors(db, get_embedder(), req.user_id, lastfm=lastfm, spotify=spotify)
    try:
        answer = await run_agent(
            llm, executors, ARG_MODELS, req.message, tool_schemas=TOOL_SCHEMAS
        )
    finally:
        await llm.aclose()
        if lastfm is not None:
            await lastfm.aclose()
        if spotify is not None:
            await spotify.aclose()
    return {"answer": answer}
