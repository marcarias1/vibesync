"""Verifica el ENSAMBLAJE end-to-end de los executors del agente:
- que el filtro anti-comercial se aplica de verdad (no solo devuelve similares crudos),
- que el modo create/overwrite enruta correctamente.
"""
from app.agent.executors import build_executors
from app.agent.tools import PlaylistControllerArgs, SimilarUndergroundArgs
from app.enrich.embeddings import FakeEmbedder


class FakeLastFm:
    DATA = {
        "Underground Src": {"listeners": 20_000, "tags": ["neoperreo", "trap latino"]},
        "Kept Under": {"listeners": 12_000, "tags": ["neoperreo", "dembow"]},
        "Mainstream Pop": {"listeners": 8_000_000, "tags": ["neoperreo", "pop"]},
    }

    async def artist_info(self, name):
        d = self.DATA.get(name, {"listeners": 1000, "tags": []})
        return {"name": name, "mbid": None, "listeners": d["listeners"],
                "playcount": d["listeners"] * 10, "tags": d["tags"]}

    async def similar_artists(self, name, limit=20):
        return ["Kept Under", "Mainstream Pop"]

    async def top_tracks(self, artist, limit=3):
        return [{"artist": artist, "name": f"{artist} Track {i}"} for i in range(1, limit + 1)]


async def test_similar_underground_filters_out_mainstream(db):
    ex = build_executors(db, FakeEmbedder(64), "u1", lastfm=FakeLastFm())
    res = await ex["find_similar_underground_tracks"](
        SimilarUndergroundArgs(source_artist="Underground Src", limit=10))
    # el underground de comercialidad similar se queda; el mainstream se descarta
    assert "Kept Under" in res["artists"]
    assert "Mainstream Pop" not in res["artists"]


class FakeSpotify:
    def __init__(self):
        self.new, self.reused, self.items = [], [], []

    async def create_new(self, user_id, name):
        self.new.append(name)
        return "PID_NEW"

    async def get_or_create(self, user_id, name):
        self.reused.append(name)
        return "PID_OLD"

    async def set_items(self, pid, uris):
        self.items.append((pid, list(uris)))


async def test_playlist_mode_routing():
    sp = FakeSpotify()
    ex = build_executors(None, FakeEmbedder(8), "u1", spotify=sp)
    a = await ex["spotify_playlist_controller"](
        PlaylistControllerArgs(playlist_name="X", track_uris=["spotify:track:a"], mode="create"))
    b = await ex["spotify_playlist_controller"](
        PlaylistControllerArgs(playlist_name="X", track_uris=["spotify:track:a"], mode="overwrite"))
    assert a["playlist_id"] == "PID_NEW" and sp.new == ["X"]      # create → nueva
    assert b["playlist_id"] == "PID_OLD" and sp.reused == ["X"]   # overwrite → reutiliza
    assert len(sp.items) == 2
