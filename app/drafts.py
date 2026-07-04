"""Flujo de BORRADORES: proponer (sin crear) → editar → publicar en Spotify.

Complementa a `app/dj.py` (que crea directo, botón "Crear ya"). Aquí el agente
propone un borrador editable que se persiste en `playlist_drafts` y solo se
escribe en Spotify al publicar.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.agent.executors import build_executors
from app.agent.llm import DeepSeekClient
from app.agent.runner import run_agent
from app.agent.tools import ARG_MODELS, TOOL_SCHEMAS
from app.config import get_settings
from app.db.client import get_db
from app.enrich.embeddings import get_embedder
from app.enrich.lastfm import LastFmClient
from app.enrich.tracks import save_draft_tracks
from app.spotify.playlists import SpotifyPlaylistController
from app.spotify.session import current_user, get_access_token

router = APIRouter(tags=["drafts"])

DRAFT_SYSTEM = (
    "Eres el DJ de VibeSync. Propón un BORRADOR de playlist, NO crees nada en Spotify. "
    "Flujo eficiente: 1) `get_user_preferences` y `get_user_music_profile` (una vez cada uno). "
    "2) `find_similar_underground_tracks` sobre 1-2 artistas — como MUCHO 2 veces (es lento). "
    "3) Reúne ~12-15 temas. "
    "OBLIGATORIO: si el usuario NOMBRA artistas o temas concretos, INCLÚYELOS SIEMPRE (aunque sean "
    "comerciales o no estén en tu BD; Spotify resuelve cualquier artista real). NUNCA omitas un "
    "artista que el usuario pidió. "
    "4) Llama YA a `proponer_playlist_draft` con la lista COMPLETA {artist,title}. "
    "5) Después llama UNA vez a `asegurar_playlist` con `requested_artists` = los artistas que el "
    "usuario nombró, para revisar huecos/faltas. NO uses `crear_playlist_spotify` ni "
    "`search_tracks_database` para descubrir. Termina con una tabla Markdown (artista · título · por qué)."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DjRequest(BaseModel):
    message: str


class DraftAddTrack(BaseModel):
    artist: str = ""
    title: str = ""
    uri: str | None = None          # si viene del buscador en vivo, ya está resuelto
    cover_url: str | None = None


class DraftEdit(BaseModel):
    remove: list[str] = []          # uris a quitar
    add: list[DraftAddTrack] = []   # temas a añadir (con uri directo o por artista/título)
    reorder: list[str] = []         # orden final por uri


class RefineReq(BaseModel):
    instruction: str                # "quita la 3 y pon algo de Yung Beef", "más oscuro"...


REFINE_SYSTEM = (
    "Eres el DJ de VibeSync EDITANDO un borrador existente. Se te da la lista actual numerada y una "
    "instrucción. Aplícala: mantén los que sigan, quita los indicados, añade nuevos con "
    "`find_similar_underground_tracks` si hace falta (MÁX 2 veces, es lento). "
    "OBLIGATORIO: MANTÉN los artistas que el usuario pide y NUNCA omitas un artista nombrado (aunque "
    "sea comercial o no esté en BD). Llama a `proponer_playlist_draft` con la lista COMPLETA "
    "resultante y luego UNA vez a `asegurar_playlist`. Respeta el veto (`get_user_preferences`). "
    "Responde con una nota breve de los cambios."
)


async def _clients(db, user_id):
    s = get_settings()
    access = await get_access_token(db, user_id)
    llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
    lastfm = LastFmClient(s.lastfm_api_key) if s.lastfm_api_key else None
    spotify = SpotifyPlaylistController(access, db=db) if access else None
    return llm, lastfm, spotify


@router.post("/dj/draft")
async def dj_draft(req: DjRequest, background: BackgroundTasks):
    db = get_db()
    user = await current_user(db)
    if not user:
        raise HTTPException(400, "No hay ningún usuario de Spotify conectado")
    user_id = user["_id"]
    llm, lastfm, spotify = await _clients(db, user_id)
    holder: dict = {}
    executors = build_executors(db, get_embedder(), user_id,
                                lastfm=lastfm, spotify=spotify, result_holder=holder)
    try:
        answer = await run_agent(llm, executors, ARG_MODELS, req.message,
                                 tool_schemas=TOOL_SCHEMAS, max_iters=16, system=DRAFT_SYSTEM,
                                 result_holder=holder)
    finally:
        await llm.aclose()
        if lastfm is not None:
            await lastfm.aclose()
        if spotify is not None:
            await spotify.aclose()

    d = holder.get("draft") or {}
    suggestions = holder.get("suggestions", [])
    draft_id = uuid.uuid4().hex
    now = _utcnow()
    doc = {
        "_id": draft_id, "user_id": user_id, "prompt": req.message,
        "name": d.get("name") or "VibeSync Draft", "status": "draft",
        "tracks": d.get("tracks", []), "not_found": d.get("not_found", []),
        "suggestions": suggestions,
        "created_at": now, "updated_at": now,
    }
    await db["playlist_drafts"].insert_one(doc)
    # en background: guarda los tracks resueltos en `tracks` (embeddings) → la búsqueda semántica crece
    if doc["tracks"]:
        background.add_task(save_draft_tracks, db, doc["tracks"], embedder=get_embedder())
    return {"draft_id": draft_id, "name": doc["name"], "tracks": doc["tracks"],
            "not_found": doc["not_found"], "answer": answer, "suggestions": suggestions}


@router.patch("/dj/draft/{draft_id}")
async def edit_draft(draft_id: str, edit: DraftEdit):
    db = get_db()
    draft = await db["playlist_drafts"].find_one({"_id": draft_id})
    if not draft:
        raise HTTPException(404, "Borrador no encontrado")
    tracks = draft.get("tracks", [])

    if edit.remove:
        rem = set(edit.remove)
        tracks = [t for t in tracks if t.get("uri") not in rem]

    if edit.add:
        access = await get_access_token(db, draft["user_id"])
        ctrl = SpotifyPlaylistController(access, db=db) if access else None
        try:
            for a in edit.add:
                if not a.uri and not (a.artist.strip() or a.title.strip()):
                    continue  # nada que añadir
                if a.uri:  # ya resuelto por el buscador en vivo
                    tracks.append({"artist": a.artist, "title": a.title,
                                   "uri": a.uri, "cover_url": a.cover_url})
                    continue
                found = await ctrl.search_track(a.artist, a.title) if ctrl else None
                tracks.append({"artist": a.artist, "title": a.title,
                               "uri": (found or {}).get("uri"),
                               "cover_url": (found or {}).get("cover_url")})
        finally:
            if ctrl is not None:
                await ctrl.aclose()

    if edit.reorder:
        order = {u: i for i, u in enumerate(edit.reorder)}
        tracks.sort(key=lambda t: order.get(t.get("uri"), 10_000))

    await db["playlist_drafts"].update_one(
        {"_id": draft_id}, {"$set": {"tracks": tracks, "updated_at": _utcnow()}})
    return {"draft_id": draft_id, "tracks": tracks}


@router.post("/dj/draft/{draft_id}/refine")
async def refine_draft(draft_id: str, req: RefineReq, background: BackgroundTasks):
    db = get_db()
    draft = await db["playlist_drafts"].find_one({"_id": draft_id})
    if not draft:
        raise HTTPException(404, "Borrador no encontrado")
    user_id = draft["user_id"]
    current = "\n".join(f"{i + 1}. {t['artist']} - {t['title']}"
                        for i, t in enumerate(draft.get("tracks", [])))
    msg = (f"Borrador actual '{draft['name']}':\n{current}\n\n"
           f"Instrucción del usuario: {req.instruction}\n"
           "Mantén los artistas que el usuario pida; no borres lo que quiere conservar.")

    llm, lastfm, spotify = await _clients(db, user_id)
    holder: dict = {}
    executors = build_executors(db, get_embedder(), user_id,
                                lastfm=lastfm, spotify=spotify, result_holder=holder)
    try:
        answer = await run_agent(llm, executors, ARG_MODELS, msg,
                                 tool_schemas=TOOL_SCHEMAS, max_iters=16, system=REFINE_SYSTEM,
                                 result_holder=holder)
    finally:
        await llm.aclose()
        if lastfm is not None:
            await lastfm.aclose()
        if spotify is not None:
            await spotify.aclose()

    d = holder.get("draft") or {}
    suggestions = holder.get("suggestions", [])
    if d.get("tracks"):
        await db["playlist_drafts"].update_one(
            {"_id": draft_id},
            {"$set": {"tracks": d["tracks"], "not_found": d.get("not_found", []),
                      "suggestions": suggestions, "updated_at": _utcnow()}})
        background.add_task(save_draft_tracks, db, d["tracks"], embedder=get_embedder())
    updated = await db["playlist_drafts"].find_one({"_id": draft_id})
    return {"draft_id": draft_id, "tracks": updated.get("tracks", []),
            "answer": answer, "suggestions": suggestions}


@router.post("/dj/draft/{draft_id}/publish")
async def publish_draft(draft_id: str):
    db = get_db()
    draft = await db["playlist_drafts"].find_one({"_id": draft_id})
    if not draft:
        raise HTTPException(404, "Borrador no encontrado")
    access = await get_access_token(db, draft["user_id"])
    if not access:
        raise HTTPException(400, "Spotify no conectado")
    ctrl = SpotifyPlaylistController(access, db=db)
    try:
        uris: list[str] = []
        for t in draft.get("tracks", []):
            uri = t.get("uri")
            if not uri:
                found = await ctrl.search_track(t["artist"], t["title"])
                uri = found["uri"] if found else None
            if uri:
                uris.append(uri)
        if not uris:
            raise HTTPException(400, "Ningún tema del borrador se pudo resolver en Spotify")
        pid = await ctrl.create_new(draft["user_id"], draft["name"])
        await ctrl.set_items(pid, uris)
        url = f"https://open.spotify.com/playlist/{pid}"
    finally:
        await ctrl.aclose()

    await db["playlist_drafts"].update_one(
        {"_id": draft_id},
        {"$set": {"status": "published", "spotify_playlist_id": pid, "url": url,
                  "updated_at": _utcnow()}})
    return {"url": url, "added": len(uris)}


@router.get("/search/tracks")
async def search_tracks_live(q: str, limit: int = 8):
    """Buscador en vivo de Spotify para añadir temas al borrador (con carátula)."""
    db = get_db()
    user = await current_user(db)
    if not user:
        return {"tracks": []}
    access = await get_access_token(db, user["_id"])
    if not access:
        return {"tracks": []}
    ctrl = SpotifyPlaylistController(access, db=db)
    try:
        return {"tracks": await ctrl.search_tracks(q, min(max(limit, 1), 10))}
    finally:
        await ctrl.aclose()


@router.get("/dj/drafts")
async def list_drafts():
    db = get_db()
    user = await current_user(db)
    if not user:
        return {"drafts": []}
    cur = db["playlist_drafts"].find({"user_id": user["_id"]}).sort("created_at", -1).limit(30)
    docs = await cur.to_list(30)
    return {"drafts": [{
        "draft_id": d["_id"], "name": d["name"], "status": d.get("status"),
        "count": len(d.get("tracks", [])), "url": d.get("url"),
        "prompt": d.get("prompt"), "created_at": d.get("created_at"),
    } for d in docs]}


@router.get("/dj/draft/{draft_id}")
async def get_draft(draft_id: str):
    db = get_db()
    d = await db["playlist_drafts"].find_one({"_id": draft_id})
    if not d:
        raise HTTPException(404, "Borrador no encontrado")
    return {"draft_id": draft_id, "name": d["name"], "status": d.get("status"),
            "tracks": d.get("tracks", []), "url": d.get("url"), "prompt": d.get("prompt")}
