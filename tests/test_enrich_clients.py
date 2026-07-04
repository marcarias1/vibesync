"""Fase 3: clientes de enriquecimiento de audio (ReccoBeats) y lyrics (lyrics.ovh)."""
import httpx
import respx

from app.enrich.audio import ReccoBeatsClient
from app.enrich.lyrics import LyricsClient


@respx.mock
async def test_reccobeats_audio_features_two_step():
    # 1) resolver spotify id -> id interno
    respx.get(url__startswith="https://api.reccobeats.com/v1/track?").mock(
        return_value=httpx.Response(200, json={"content": [{"id": "rid1"}]}))
    # 2) audio features por id interno
    respx.get(url__startswith="https://api.reccobeats.com/v1/track/rid1/audio-features").mock(
        return_value=httpx.Response(200, json={"tempo": 120, "energy": 0.7, "danceability": 0.6, "valence": 0.5}))
    c = ReccoBeatsClient()
    feats = await c.audio_features("spotifyid")
    await c.aclose()
    assert feats["tempo"] == 120 and feats["energy"] == 0.7 and feats["danceability"] == 0.6


@respx.mock
async def test_reccobeats_sin_datos():
    respx.get(url__startswith="https://api.reccobeats.com/v1/track?").mock(
        return_value=httpx.Response(200, json={"content": []}))
    c = ReccoBeatsClient()
    assert await c.audio_features("xyz") is None
    await c.aclose()


@respx.mock
async def test_lyrics_fetch():
    respx.get(url__startswith="https://api.lyrics.ovh/v1/").mock(
        return_value=httpx.Response(200, json={"lyrics": "noche oscura de trap"}))
    c = LyricsClient()
    text = await c.fetch("Bb trickz", "Missn tickz")
    await c.aclose()
    assert "trap" in text
