import httpx
import respx

from app.enrich.lastfm import LastFmClient


@respx.mock
async def test_artist_info_parses_listeners_and_tags():
    respx.get(url__startswith="https://ws.audioscrobbler.com/2.0/").mock(
        return_value=httpx.Response(200, json={"artist": {
            "name": "Bad Bunny", "mbid": "abc",
            "stats": {"listeners": "1234", "playcount": "9999"},
            "tags": {"tag": [{"name": "reggaeton"}, {"name": "trap latino"}]}}}))
    c = LastFmClient("key")
    info = await c.artist_info("Bad Bunny")
    await c.aclose()
    assert info["listeners"] == 1234 and info["playcount"] == 9999
    assert info["tags"] == ["reggaeton", "trap latino"]


@respx.mock
async def test_similar_artists():
    respx.get(url__startswith="https://ws.audioscrobbler.com/2.0/").mock(
        return_value=httpx.Response(200, json={"similarartists": {
            "artist": [{"name": "Feid"}, {"name": "Mora"}]}}))
    c = LastFmClient("key")
    sim = await c.similar_artists("Bad Bunny")
    await c.aclose()
    assert sim == ["Feid", "Mora"]
