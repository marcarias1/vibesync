"""Router del DJ: el agente genera la playlist y la crea en Spotify de verdad."""
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
from app.spotify.session import current_user, get_access_token

router = APIRouter(tags=["dj"])

DJ_SYSTEM = (
    "Eres el DJ de VibeSync. Flujo: 1) `get_user_music_profile` para el contexto (una vez). "
    "2) `find_similar_underground_tracks` sobre 1-2 artistas del usuario — devuelve TRACKS "
    "underground (artista+título) ya filtrados de lo comercial. 3) Reúne ~12-15 temas y llama a "
    "`crear_playlist_spotify` con el nombre y la lista de {artist,title} para CREARLA en Spotify. "
    "No uses `search_tracks_database` para descubrir (solo tiene el historial del usuario). "
    "Tras crearla, responde en Markdown con una tabla (artista · título · por qué encaja) y una "
    "explicación breve de por qué la selección es underground y no comercial."
)


class DjRequest(BaseModel):
    message: str


@router.post("/dj/create")
async def dj_create(req: DjRequest):
    s = get_settings()
    db = get_db()
    user = await current_user(db)
    if not user:
        raise HTTPException(400, "No hay ningún usuario de Spotify conectado")
    user_id = user["_id"]
    access = await get_access_token(db, user_id)

    llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
    lastfm = LastFmClient(s.lastfm_api_key) if s.lastfm_api_key else None
    spotify = SpotifyPlaylistController(access, db=db) if access else None
    holder: dict = {}
    executors = build_executors(db, get_embedder(), user_id,
                                lastfm=lastfm, spotify=spotify, result_holder=holder)
    try:
        answer = await run_agent(llm, executors, ARG_MODELS, req.message,
                                 tool_schemas=TOOL_SCHEMAS, max_iters=12, system=DJ_SYSTEM)
    finally:
        await llm.aclose()
        if lastfm is not None:
            await lastfm.aclose()
        if spotify is not None:
            await spotify.aclose()

    pl = holder.get("playlist") or {}
    return {"answer": answer, "playlist_url": pl.get("url"),
            "playlist_name": pl.get("name"), "added": pl.get("added", 0)}
