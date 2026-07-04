"""OAuth 2.0 con PKCE para Spotify (sin client secret)."""
import base64
import hashlib
import secrets
import urllib.parse

import httpx

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_pkce() -> tuple[str, str]:
    """Devuelve (code_verifier, code_challenge) con método S256."""
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def authorize_url(client_id: str, redirect_uri: str, scopes: list[str],
                  state: str, code_challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(client_id: str, code: str, redirect_uri: str,
                        code_verifier: str, client: httpx.AsyncClient | None = None) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    c = client or httpx.AsyncClient(timeout=10.0)
    try:
        r = await c.post(TOKEN_URL, data=data)
        r.raise_for_status()
        return r.json()
    finally:
        if client is None:
            await c.aclose()


async def refresh_token(client_id: str, refresh: str,
                        client: httpx.AsyncClient | None = None) -> dict:
    data = {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id}
    c = client or httpx.AsyncClient(timeout=10.0)
    try:
        r = await c.post(TOKEN_URL, data=data)
        r.raise_for_status()
        return r.json()
    finally:
        if client is None:
            await c.aclose()
