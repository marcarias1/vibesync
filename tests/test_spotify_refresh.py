"""Test de refresh_token de Spotify con respx."""
import httpx
import respx

from app.spotify.auth import refresh_token


@respx.mock
async def test_refresh_token_devuelve_nuevo_access_token():
    route = respx.post("https://accounts.spotify.com/api/token").mock(
        return_value=httpx.Response(200, json={"access_token": "nuevo_tok", "token_type": "Bearer"})
    )
    res = await refresh_token("cid", "refresh_xyz")

    assert res["access_token"] == "nuevo_tok"
    assert route.called
