"""Construye/actualiza la colección `tracks` desde el histórico + artistas enriquecidos.

Objetivo: que la búsqueda semántica (vector) y el filtro anti-comercial operen a
nivel TRACK. Denormaliza del artista `commerciality_score`, `tags` y añade
`play_count` (para el filtro `min_plays`) y el `embedding` del perfil textual.
"""
from datetime import datetime, timezone


async def _artist_doc(db, artist_name: str) -> dict | None:
    if not artist_name:
        return None
    doc = await db["artists"].find_one({"name": artist_name})
    if doc is None:  # el _id puede ser el nombre normalizado
        doc = await db["artists"].find_one({"_id": artist_name.lower()})
    return doc


async def rebuild_tracks(db, user_id: str, *, embedder) -> int:
    """Un doc en `tracks` por cada track distinto del histórico del usuario."""
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": "$track_uri",
            "name": {"$first": "$track_name"},
            "artist_name": {"$first": "$artist_name"},
            "play_count": {"$sum": 1},
        }},
    ]
    cursor = await db["playback_history"].aggregate(pipeline)
    rows = await cursor.to_list(None)

    count = 0
    for r in rows:
        artist_name = r.get("artist_name") or ""
        artist = await _artist_doc(db, artist_name)
        tags = (artist or {}).get("tags", [])
        # perfil textual = nombre track + artista + tags → embedding
        text = " — ".join(p for p in [r.get("name") or "", artist_name, ", ".join(tags)] if p)
        await db["tracks"].update_one(
            {"_id": r["_id"]},
            {"$set": {
                "uri": r["_id"],
                "name": r.get("name"),
                "artist_name": artist_name,
                "tags": tags,
                "commerciality_score": (artist or {}).get("commerciality_score"),
                "play_count": r["play_count"],
                "embedding": embedder.encode(text),
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
        count += 1
    return count
