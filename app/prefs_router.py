"""Endpoints de feedback (👍/👎/bloqueo) y de preferencias (panel de gustos)."""
import contextlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.client import get_db
from app.enrich.taste import rebuild_taste
from app.preferences import apply_feedback, get_preferences, save_preferences
from app.spotify.session import current_user

router = APIRouter(tags=["preferences"])

_VERDICTS = {"like", "dislike", "remove", "block"}


class FeedbackIn(BaseModel):
    verdict: str
    artist: str | None = None
    track_uri: str | None = None
    tag: str | None = None


@router.post("/feedback")
async def post_feedback(fb: FeedbackIn):
    if fb.verdict not in _VERDICTS:
        raise HTTPException(400, "verdict debe ser like|dislike|remove|block")
    db = get_db()
    user = await current_user(db)
    if not user:
        raise HTTPException(400, "No hay usuario conectado")
    uid = user["_id"]
    if fb.track_uri:
        await db["feedback"].update_one(
            {"_id": f"{uid}:{fb.track_uri}"},
            {"$set": {"user_id": uid, "track_uri": fb.track_uri, "artist": fb.artist,
                      "verdict": fb.verdict, "tag": fb.tag, "ts": datetime.now(timezone.utc)}},
            upsert=True)
    prefs = await get_preferences(db, uid)
    patch = apply_feedback(prefs, verdict=fb.verdict, artist=fb.artist, tag=fb.tag)
    await save_preferences(db, uid, patch)
    with contextlib.suppress(Exception):  # recalcula el perfil de gusto con el nuevo feedback
        await rebuild_taste(db, uid)
    return {"ok": True, "blocked": patch["blocked_artists"],
            "disliked": list(patch["disliked_artists"].keys()),
            "loved": patch["loved_artists"]}


class PrefsPatch(BaseModel):
    underground_level: int | None = None
    blocked_artists: list[str] | None = None
    loved_artists: list[str] | None = None
    loved_tags: list[str] | None = None


@router.get("/preferences")
async def read_prefs():
    db = get_db()
    user = await current_user(db)
    if not user:
        return {}
    p = await get_preferences(db, user["_id"])
    p.pop("_id", None)
    p.pop("content_centroid", None)  # no exponer vectores grandes a la UI
    p.pop("lyrics_centroid", None)
    return p


@router.put("/preferences")
async def update_prefs(patch: PrefsPatch):
    db = get_db()
    user = await current_user(db)
    if not user:
        raise HTTPException(400, "No hay usuario conectado")
    data = {k: v for k, v in patch.model_dump().items() if v is not None}
    if "underground_level" in data:
        data["underground_level"] = max(0, min(100, data["underground_level"]))
    await save_preferences(db, user["_id"], data)
    return {"ok": True, **data}
