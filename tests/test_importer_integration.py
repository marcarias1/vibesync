"""Integración contra Mongo real: idempotencia del importador + agregación de counts."""
from datetime import datetime, timezone

from app.ingest.aggregations import recompute_user_vibe
from app.ingest.importer import ingest

BASE = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)


def _raw() -> list[dict]:
    entries = []
    for i in range(3):  # 3 plays de A (válidos)
        entries.append({
            "ts": BASE.replace(minute=i).isoformat(), "ms_played": 60000,
            "spotify_track_uri": "spotify:track:A", "reason_end": "trackdone",
            "master_metadata_track_name": "TA", "master_metadata_album_artist_name": "Artist"})
    entries.append({  # 1 play de B
        "ts": BASE.replace(hour=11).isoformat(), "ms_played": 60000,
        "spotify_track_uri": "spotify:track:B", "reason_end": "trackdone"})
    entries.append({  # ruido: < 30s -> filtrado
        "ts": BASE.replace(hour=12).isoformat(), "ms_played": 5000,
        "spotify_track_uri": "spotify:track:A", "reason_end": "trackdone"})
    entries.append({  # ruido: skip -> filtrado
        "ts": BASE.replace(hour=13).isoformat(), "ms_played": 60000,
        "spotify_track_uri": "spotify:track:A", "reason_end": "fwdbtn"})
    return entries


async def test_ingest_is_idempotent(db):
    r1 = await ingest(db, "u1", _raw())
    assert r1.kept == 4 and r1.inserted == 4      # 2 ruidos filtrados

    r2 = await ingest(db, "u1", _raw())           # resubida del mismo fichero
    assert r2.inserted == 0 and r2.duplicates == 4

    assert await db["playback_history"].count_documents({"user_id": "u1"}) == 4


async def test_recompute_vibe_counts_and_is_idempotent(db):
    await ingest(db, "u1", _raw())
    await recompute_user_vibe(db, "u1")

    a = await db["user_tracks_vibe"].find_one({"_id": "u1:spotify:track:A"})
    b = await db["user_tracks_vibe"].find_one({"_id": "u1:spotify:track:B"})
    assert a["play_count"] == 3 and a["total_ms"] == 180000
    assert b["play_count"] == 1

    await recompute_user_vibe(db, "u1")           # recalcular NO dobla (no es $inc)
    a2 = await db["user_tracks_vibe"].find_one({"_id": "u1:spotify:track:A"})
    assert a2["play_count"] == 3
