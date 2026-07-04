"""Preferencias de usuario: lectura/escritura + aprendizaje ligero por feedback.

'Bloqueo ligero que aprende': un dislike no veta para siempre — sube un peso que,
al acumularse, deja de proponer al artista (umbral). Un `block` explícito sí veta.
Un `like` revierte el dislike y marca como amado.
"""
from datetime import datetime, timezone

from app.db.models import _default_weights

DISLIKE_STEP = 1.0
DISLIKE_CAP = 5.0
SOFT_BLOCK_THRESHOLD = 3.0  # a partir de aquí, el bloqueo ligero deja de proponerlo


def default_prefs(user_id: str) -> dict:
    return {
        "_id": user_id, "blocked_artists": [], "disliked_artists": {}, "disliked_tags": {},
        "loved_artists": [], "loved_tags": [], "underground_level": 50,
        "content_centroid": None, "lyrics_centroid": None, "audio_profile": None,
        "weights": _default_weights(),
    }


async def get_preferences(db, user_id: str) -> dict:
    return await db["user_preferences"].find_one({"_id": user_id}) or default_prefs(user_id)


async def save_preferences(db, user_id: str, patch: dict) -> None:
    await db["user_preferences"].update_one(
        {"_id": user_id}, {"$set": {**patch, "updated_at": datetime.now(timezone.utc)}}, upsert=True)


def apply_feedback(prefs: dict, *, verdict: str, artist: str | None = None,
                   tag: str | None = None) -> dict:
    """Devuelve el patch a persistir (aprendizaje ligero, sin ban salvo 'block')."""
    disliked = dict(prefs.get("disliked_artists", {}))
    blocked = list(prefs.get("blocked_artists", []))
    loved = list(prefs.get("loved_artists", []))
    dtags = dict(prefs.get("disliked_tags", {}))
    ltags = list(prefs.get("loved_tags", []))

    if verdict == "block" and artist:
        if artist not in blocked:
            blocked.append(artist)
    elif verdict in ("dislike", "remove") and artist:
        disliked[artist] = min(DISLIKE_CAP, disliked.get(artist, 0.0) + DISLIKE_STEP)
    elif verdict == "like" and artist:
        if artist not in loved:
            loved.append(artist)
        disliked.pop(artist, None)  # un like revierte el dislike

    if tag:
        if verdict in ("dislike", "remove"):
            dtags[tag] = min(DISLIKE_CAP, dtags.get(tag, 0.0) + DISLIKE_STEP)
        elif verdict == "like" and tag not in ltags:
            ltags.append(tag)

    return {"disliked_artists": disliked, "blocked_artists": blocked,
            "loved_artists": loved, "disliked_tags": dtags, "loved_tags": ltags}


def blocked_set(prefs: dict) -> set[str]:
    """Artistas efectivamente vetados (en minúsculas): blocked duros + disliked sobre umbral."""
    hard = set(prefs.get("blocked_artists", []))
    soft = {a for a, w in prefs.get("disliked_artists", {}).items() if w >= SOFT_BLOCK_THRESHOLD}
    return {a.lower() for a in (hard | soft)}
