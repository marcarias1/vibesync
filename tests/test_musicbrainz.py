"""Tests del cliente MusicBrainz con respx (sin tocar la red real)."""
import httpx
import respx

from app.enrich.musicbrainz import MusicBrainzClient


@respx.mock
async def test_search_artist_parsea_mbid_name_genres():
    # Mock del endpoint de búsqueda de artistas.
    respx.get(url__startswith="https://musicbrainz.org/ws/2/artist").mock(
        return_value=httpx.Response(200, json={"artists": [{
            "id": "mbid-123",
            "name": "Radiohead",
            "genres": [{"name": "alternative rock"}, {"name": "art rock"}],
        }]})
    )
    c = MusicBrainzClient("vibesync/0.1")
    info = await c.search_artist("Radiohead")
    await c.aclose()

    assert info["mbid"] == "mbid-123"
    assert info["name"] == "Radiohead"
    assert info["genres"] == ["alternative rock", "art rock"]


@respx.mock
async def test_search_artist_sin_resultados_devuelve_none():
    # Sin artistas → None.
    respx.get(url__startswith="https://musicbrainz.org/ws/2/artist").mock(
        return_value=httpx.Response(200, json={"artists": []})
    )
    c = MusicBrainzClient("vibesync/0.1")
    info = await c.search_artist("noexisteesteartista")
    await c.aclose()

    assert info is None
