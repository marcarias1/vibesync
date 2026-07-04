"""Fase 1: el executor `proponer_playlist_draft` construye tracks estructurados
(con uri + carátula) SIN crear nada en Spotify."""
from app.agent.executors import build_executors
from app.agent.tools import CreatePlaylistArgs
from app.enrich.embeddings import FakeEmbedder


class FakeSpotify:
    """search_track determinista con carátula, sin red."""
    async def search_track(self, artist, title):
        key = f"{artist}_{title}".replace(" ", "").lower()
        return {"uri": f"spotify:track:{key}", "name": title, "artist": artist,
                "cover_url": f"https://img.example/{key}.jpg"}


async def test_proponer_draft_estructura_sin_crear():
    holder: dict = {}
    ex = build_executors(None, FakeEmbedder(8), "u1",
                         spotify=FakeSpotify(), result_holder=holder)
    args = CreatePlaylistArgs(playlist_name="Mi Borrador", tracks=[
        {"artist": "Mora", "title": "Volando"},
        {"artist": "Feid", "title": "Classy 101"},
    ])
    res = await ex["proponer_playlist_draft"](args)

    assert res["proposed"] == 2
    assert res["not_found"] == []
    draft = holder["draft"]
    assert draft["name"] == "Mi Borrador"
    assert len(draft["tracks"]) == 2
    # cada track tiene uri + carátula resueltas (para las tarjetas)
    assert all(t["uri"] and t["cover_url"] for t in draft["tracks"])
    assert draft["tracks"][0]["artist"] == "Mora"


async def test_proponer_draft_sin_spotify_deja_uris_nulas():
    holder: dict = {}
    ex = build_executors(None, FakeEmbedder(8), "u1", spotify=None, result_holder=holder)
    args = CreatePlaylistArgs(playlist_name="X", tracks=[{"artist": "A", "title": "B"}])
    await ex["proponer_playlist_draft"](args)
    t = holder["draft"]["tracks"][0]
    assert t["uri"] is None and t["cover_url"] is None  # sin token no resuelve, pero propone
