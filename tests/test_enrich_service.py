"""Tests del servicio de enriquecimiento (todo con fakes, sin red real)."""
import pytest

from app.config import get_settings
from app.enrich.embeddings import FakeEmbedder
from app.enrich.service import enrich_artist, enrich_artists

pytestmark = pytest.mark.asyncio


# Datos canónicos: mainstream (muchos listeners) vs underground (pocos).
_ARTISTS = {
    "Coldplay": {
        "name": "Coldplay",
        "mbid": None,
        "listeners": 4_000_000,
        "playcount": 200_000_000,
        "tags": ["Rock", "  Pop ", "rock"],  # con mayúsculas, espacios y duplicado
    },
    "Obscure Band": {
        "name": "Obscure Band",
        "mbid": None,
        "listeners": 1_200,
        "playcount": 5_000,
        "tags": ["Lo-Fi", "Experimental"],
    },
}


class FakeLastFm:
    """Devuelve datos canónicos sin tocar la red."""

    async def artist_info(self, artist: str) -> dict:
        return dict(_ARTISTS[artist])

    async def similar_artists(self, artist: str, limit: int = 20) -> list[str]:
        return []


@pytest.fixture
def embedder():
    return FakeEmbedder(get_settings().embedding_dim)


async def test_enrich_persiste_score_tags_y_embedding(db, embedder):
    doc = await enrich_artist(db, "Coldplay", lastfm=FakeLastFm(), embedder=embedder)

    # commerciality_score guardado y en rango.
    assert doc["commerciality_score"] > 0
    assert 0.0 <= doc["commerciality_score"] <= 100.0

    # embedding con longitud == embedding_dim.
    assert len(doc["embedding"]) == get_settings().embedding_dim

    # tags normalizados (minúsculas, sin espacios) y sin duplicados.
    assert doc["tags"] == ["rock", "pop"]

    # listeners persistidos.
    assert doc["lastfm_listeners"] == 4_000_000
    assert doc["updated_at"] is not None


async def test_mas_listeners_mayor_score(db, embedder):
    docs = await enrich_artists(
        db, ["Coldplay", "Obscure Band"], lastfm=FakeLastFm(), embedder=embedder
    )
    by_name = {d["name"]: d for d in docs}
    assert (
        by_name["Coldplay"]["commerciality_score"]
        > by_name["Obscure Band"]["commerciality_score"]
    )


async def test_upsert_idempotente_no_duplica(db, embedder):
    # Dos llamadas al mismo artista → un único doc.
    await enrich_artist(db, "Coldplay", lastfm=FakeLastFm(), embedder=embedder)
    await enrich_artist(db, "Coldplay", lastfm=FakeLastFm(), embedder=embedder)

    count = await db["artists"].count_documents({})
    assert count == 1
