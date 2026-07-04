"""Enriquecimiento de features por track: audio (ReccoBeats) + lyrics (embedding).

Puebla `tracks.audio` y `tracks.lyrics_embedding` para que `score_track` active
las señales de RITMO y LETRA. Pensado para correr en background (lento: varias
llamadas externas por track), no en la request del borrador.
"""
from datetime import datetime, timezone


async def enrich_track_features(db, track: dict, *, recco, lyrics_client, embedder) -> dict:
    """Enriquece un doc de `tracks` (con _id) con audio + embedding de la letra."""
    patch: dict = {}
    uri = track.get("uri") or ""
    if uri.startswith("spotify:track:"):
        feats = await recco.audio_features(uri.split(":")[-1])
        if feats:
            patch["audio"] = feats
    lyr = await lyrics_client.fetch(track.get("artist_name") or "", track.get("name") or "")
    if lyr:
        patch["lyrics_embedding"] = embedder.encode(lyr[:2000])
    if patch and track.get("_id") is not None:
        await db["tracks"].update_one(
            {"_id": track["_id"]},
            {"$set": {**patch, "updated_at": datetime.now(timezone.utc)}})
    return patch


async def enrich_user_tracks(db, *, recco, lyrics_client, embedder, limit: int = 80) -> dict:
    """Enriquece los tracks que aún no tengan audio (batch acotado)."""
    docs = await db["tracks"].find({"audio": {"$exists": False}}).limit(limit).to_list(limit)
    audio_n = lyrics_n = 0
    for d in docs:
        patch = await enrich_track_features(db, d, recco=recco, lyrics_client=lyrics_client, embedder=embedder)
        audio_n += int("audio" in patch)
        lyrics_n += int("lyrics_embedding" in patch)
    return {"processed": len(docs), "audio": audio_n, "lyrics": lyrics_n}
