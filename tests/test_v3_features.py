"""Tests de las mejoras v3: no-agotar-pasos, ensure, enrich TTL, previews, save_draft_tracks."""
from datetime import datetime, timedelta, timezone

import httpx
import respx

from app.agent.executors import _is_stale, build_executors
from app.agent.llm import ChatResult, FakeLLM, ToolCall
from app.agent.runner import run_agent
from app.agent.tools import EnsureArgs
from app.enrich.embeddings import FakeEmbedder
from app.enrich.preview import resolve_preview
from app.enrich.tracks import save_draft_tracks


# --- Fix 1: run_agent devuelve el borrador aunque agote pasos ---------------- #
async def test_run_agent_returns_draft_on_max_iters():
    loop = ChatResult(tool_calls=[ToolCall("c", "noop", {})])
    llm = FakeLLM([loop, loop, loop, loop])

    async def noop(args):
        return {"ok": True}

    holder = {"draft": {"name": "X", "tracks": [{"uri": "spotify:track:1"}]}}
    out = await run_agent(llm, {"noop": noop}, {}, "x", max_iters=3, result_holder=holder)
    assert "borrador" in out.lower()  # mensaje coherente, no la string seca


async def test_run_agent_sin_holder_da_mensaje_generico():
    loop = ChatResult(tool_calls=[ToolCall("c", "noop", {})])
    llm = FakeLLM([loop, loop, loop])

    async def noop(args):
        return {"ok": True}

    out = await run_agent(llm, {"noop": noop}, {}, "x", max_iters=2)
    assert "No pude completar" in out


# --- Fix 2: enrich con frescura (TTL) --------------------------------------- #
def test_is_stale():
    assert _is_stale(None) is True
    assert _is_stale({}) is True
    assert _is_stale({"updated_at": datetime.now(timezone.utc)}) is False
    assert _is_stale({"updated_at": datetime.now(timezone.utc) - timedelta(days=40)}) is True


# --- Fix 5: ensure sugiere rellenos y añadidos ------------------------------ #
class _FakeSpotify:
    async def search_track(self, artist, title):
        return {"uri": f"spotify:track:{abs(hash((artist, title))) % 10000}",
                "artist": artist, "name": title, "cover_url": "c"}


class _FakeLastFm:
    async def top_tracks(self, artist, limit=3):
        return [{"artist": artist, "name": f"{artist} Top"}]

    async def similar_artists(self, name, limit=20):
        return ["Otro Under"]


async def test_asegurar_playlist_suggests_fill_and_add():
    holder = {"draft": {"name": "X",
                        "tracks": [{"artist": "A", "title": "t1", "uri": "spotify:track:1", "score": 55}],
                        "not_found": ["Ghost - Lost"]}}
    ex = build_executors(None, FakeEmbedder(8), "u1",
                         lastfm=_FakeLastFm(), spotify=_FakeSpotify(), result_holder=holder)
    res = await ex["asegurar_playlist"](EnsureArgs(requested_artists=["Nueva"]))
    types = {s["type"] for s in holder["suggestions"]}
    assert "fill" in types   # rellena el 'Ghost - Lost' no encontrado
    assert "add" in types    # añade 'Nueva' que el usuario pidió y no estaba
    assert res["suggestions"] >= 2


# --- Fix 3: preview Deezer → iTunes ----------------------------------------- #
@respx.mock
async def test_preview_deezer_first():
    respx.get(url__startswith="https://api.deezer.com/search").mock(
        return_value=httpx.Response(200, json={"data": [{"preview": "https://cdn/x.mp3"}]}))
    assert await resolve_preview("Bad Bunny", "Tití") == {"preview_url": "https://cdn/x.mp3", "source": "deezer"}


@respx.mock
async def test_preview_falls_back_to_itunes():
    respx.get(url__startswith="https://api.deezer.com/search").mock(
        return_value=httpx.Response(200, json={"data": []}))
    respx.get(url__startswith="https://itunes.apple.com/search").mock(
        return_value=httpx.Response(200, json={"results": [{"previewUrl": "https://apple/y.m4a"}]}))
    assert await resolve_preview("X", "Y") == {"preview_url": "https://apple/y.m4a", "source": "itunes"}


@respx.mock
async def test_preview_none_when_both_empty():
    respx.get(url__startswith="https://api.deezer.com/search").mock(
        return_value=httpx.Response(200, json={"data": []}))
    respx.get(url__startswith="https://itunes.apple.com/search").mock(
        return_value=httpx.Response(200, json={"results": []}))
    assert await resolve_preview("X", "Y") is None


# --- Fix 4: save_draft_tracks puebla `tracks` con embedding ----------------- #
async def test_save_draft_tracks_upserts_with_embedding(db):
    await db["tracks"].delete_many({"_id": "spotify:track:vibetest"})
    n = await save_draft_tracks(db, [
        {"artist": "A", "title": "Song", "uri": "spotify:track:vibetest", "cover_url": "c"},
        {"artist": "B", "title": "NoUri", "uri": None},
    ], embedder=FakeEmbedder(32))
    assert n == 1  # solo el que tiene uri real de Spotify
    doc = await db["tracks"].find_one({"_id": "spotify:track:vibetest"})
    assert doc and len(doc["embedding"]) == 32 and doc["name"] == "Song"
    await db["tracks"].delete_many({"_id": "spotify:track:vibetest"})
