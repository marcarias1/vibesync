import httpx
import respx

from app.spotify.playlists import SpotifyPlaylistController, chunk_uris


def test_chunk_uris_caps_at_100():
    uris = [f"spotify:track:{i}" for i in range(250)]
    chunks = list(chunk_uris(uris))
    assert [len(c) for c in chunks] == [100, 100, 50]


@respx.mock
async def test_set_items_uses_put_then_post_for_overflow():
    put = respx.put("https://api.spotify.com/v1/playlists/PID/items").mock(
        return_value=httpx.Response(200, json={"snapshot_id": "s"}))
    post = respx.post("https://api.spotify.com/v1/playlists/PID/items").mock(
        return_value=httpx.Response(200, json={"snapshot_id": "s"}))

    ctrl = SpotifyPlaylistController("tok")
    await ctrl.set_items("PID", [f"spotify:track:{i}" for i in range(150)])
    await ctrl.aclose()

    assert put.called and put.call_count == 1       # primeros 100 (reemplaza)
    assert post.called and post.call_count == 1     # 50 restantes (añade)
