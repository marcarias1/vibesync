import base64
import hashlib

import httpx
import respx

from app.spotify.auth import authorize_url, exchange_code, generate_pkce


def test_pkce_challenge_is_s256_of_verifier():
    verifier, challenge = generate_pkce()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    assert challenge == expected
    assert 43 <= len(verifier) <= 128   # rango que exige la spec PKCE


def test_authorize_url_has_required_params():
    url = authorize_url("cid", "http://cb", ["user-top-read"], "state123", "chal")
    assert url.startswith("https://accounts.spotify.com/authorize?")
    for frag in ("client_id=cid", "code_challenge_method=S256", "code_challenge=chal", "state=state123"):
        assert frag in url


@respx.mock
async def test_exchange_code():
    route = respx.post("https://accounts.spotify.com/api/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "refresh_token": "ref"})
    )
    res = await exchange_code("cid", "code", "http://cb", "verifier")
    assert res["access_token"] == "tok"
    assert route.called
