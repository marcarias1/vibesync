"""Tests de rebuild_user_stats: correctitud del resumen e idempotencia."""
import pytest

from app.ingest.importer import ingest
from app.ingest.stats import rebuild_user_stats

USER = "user_stats_test"


def _entry(track_uri, name, artist, ts, ms=120_000):
    """Registro crudo estilo GDPR de Spotify (supera el filtro de 30s)."""
    return {
        "ts": ts,
        "ms_played": ms,
        "spotify_track_uri": track_uri,
        "master_metadata_track_name": name,
        "master_metadata_album_artist_name": artist,
        "reason_start": "trackdone",
        "reason_end": "trackdone",
        "shuffle": False,
        "skipped": False,
        "platform": "test",
    }


# Datos de ejemplo: 3 tracks, distintas horas (UTC → $hour determinista).
#   A: 3 reproducciones a las 14h  (top track)
#   B: 2 reproducciones a las 09h
#   C: 1 reproducción  a las 22h
# total_plays=6, distinct_tracks=3
RAW = [
    _entry("spotify:track:A", "Alpha", "ArtA", "2026-01-05T14:00:00Z"),
    _entry("spotify:track:A", "Alpha", "ArtA", "2026-01-05T14:15:00Z"),
    _entry("spotify:track:A", "Alpha", "ArtA", "2026-01-06T14:30:00Z"),
    _entry("spotify:track:B", "Beta", "ArtB", "2026-01-05T09:00:00Z"),
    _entry("spotify:track:B", "Beta", "ArtB", "2026-01-06T09:10:00Z"),
    _entry("spotify:track:C", "Gamma", "ArtC", "2026-01-05T22:00:00Z"),
]


@pytest.mark.asyncio
async def test_rebuild_user_stats(db):
    # La fixture db NO limpia user_stats_cache: lo hacemos aquí.
    await db["user_stats_cache"].delete_many({})

    res = await ingest(db, USER, RAW)
    assert res.inserted == 6

    doc = await rebuild_user_stats(db, USER)

    # Totales.
    assert doc["total_plays"] == 6
    assert doc["distinct_tracks"] == 3

    # Top track correcto: A con 3 reproducciones.
    assert doc["top_tracks"][0]["track_uri"] == "spotify:track:A"
    assert doc["top_tracks"][0]["plays"] == 3
    assert doc["top_tracks"][0]["name"] == "Alpha"

    # Top artista coherente.
    assert doc["top_artists"][0]["artist"] == "ArtA"
    assert doc["top_artists"][0]["plays"] == 3

    # Patrón horario: bucket 14 con 3, 09 con 2, 22 con 1.
    assert len(doc["hourly_pattern"]) == 24
    assert doc["hourly_pattern"][14] == 3
    assert doc["hourly_pattern"][9] == 2
    assert doc["hourly_pattern"][22] == 1
    assert sum(doc["hourly_pattern"]) == 6

    # Patrón semanal: 7 buckets, suma total.
    assert len(doc["weekday_pattern"]) == 7
    assert sum(doc["weekday_pattern"]) == 6


@pytest.mark.asyncio
async def test_rebuild_is_idempotent(db):
    await db["user_stats_cache"].delete_many({})

    await ingest(db, USER, RAW)

    await rebuild_user_stats(db, USER)
    await rebuild_user_stats(db, USER)

    # Un solo doc por usuario tras dos reconstrucciones.
    count = await db["user_stats_cache"].count_documents({"_id": USER})
    assert count == 1

    doc = await db["user_stats_cache"].find_one({"_id": USER})
    assert doc["total_plays"] == 6
    assert doc["distinct_tracks"] == 3
