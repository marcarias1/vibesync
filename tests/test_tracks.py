"""Verifica el seeding de `tracks`: embeddings, play_count y denormalización."""
from datetime import datetime, timezone

from app.config import get_settings
from app.enrich.embeddings import FakeEmbedder
from app.enrich.tracks import rebuild_tracks
from app.ingest.importer import ingest

BASE = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)


def _raw() -> list[dict]:
    out = []
    for i in range(3):
        out.append({"ts": BASE.replace(minute=i).isoformat(), "ms_played": 60000,
                    "spotify_track_uri": "spotify:track:A", "reason_end": "trackdone",
                    "master_metadata_track_name": "Tema A",
                    "master_metadata_album_artist_name": "Artista X"})
    out.append({"ts": BASE.replace(hour=11).isoformat(), "ms_played": 60000,
                "spotify_track_uri": "spotify:track:B", "reason_end": "trackdone",
                "master_metadata_track_name": "Tema B",
                "master_metadata_album_artist_name": "Artista Y"})
    return out


async def test_rebuild_tracks_populates_embeddings_and_playcount(db):
    dim = get_settings().embedding_dim
    # artista X pre-enriquecido → sus tags/score deben denormalizarse al track
    await db["artists"].insert_one(
        {"_id": "artista x", "name": "Artista X", "tags": ["neoperreo"], "commerciality_score": 42.0})

    await ingest(db, "u1", _raw())
    n = await rebuild_tracks(db, "u1", embedder=FakeEmbedder(dim))
    assert n == 2

    a = await db["tracks"].find_one({"_id": "spotify:track:A"})
    assert a["uri"] == "spotify:track:A"
    assert a["play_count"] == 3
    assert len(a["embedding"]) == dim
    assert a["tags"] == ["neoperreo"]           # denormalizado del artista
    assert a["commerciality_score"] == 42.0     # denormalizado del artista

    b = await db["tracks"].find_one({"_id": "spotify:track:B"})
    assert b["play_count"] == 1
    assert b["commerciality_score"] is None      # artista Y sin enriquecer
