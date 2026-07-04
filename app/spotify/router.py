"""Router OAuth PKCE de Spotify (/auth/login, /auth/callback).

Sin secretos: flujo PKCE puro. El code_verifier se guarda en memoria por `state`
(para producción multi-proceso: mover a Redis).
"""
import secrets

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.db.client import get_db
from app.security.crypto import encrypt
from app.spotify.auth import authorize_url, exchange_code, generate_pkce

router = APIRouter(prefix="/auth", tags=["auth"])

_PKCE_STORE: dict[str, str] = {}  # state -> code_verifier

SCOPES = [
    "user-top-read",
    "user-read-recently-played",
    "playlist-modify-private",
    "playlist-modify-public",
]


@router.get("/status")
async def status():
    user = await get_db()["users"].find_one({}, sort=[("_id", 1)])
    if not user:
        return {"logged_in": False}
    return {"logged_in": True, "user_id": user["_id"], "display_name": user.get("display_name")}


@router.get("/login")
async def login():
    s = get_settings()
    if not s.spotify_client_id:
        raise HTTPException(400, "SPOTIFY_CLIENT_ID no configurada")
    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(16)
    _PKCE_STORE[state] = verifier
    return {"authorize_url": authorize_url(
        s.spotify_client_id, s.spotify_redirect_uri, SCOPES, state, challenge)}


@router.get("/callback")
async def callback(code: str = Query(...), state: str = Query(...)):
    verifier = _PKCE_STORE.pop(state, None)
    if verifier is None:
        raise HTTPException(400, "state desconocido o expirado")
    s = get_settings()
    tokens = await exchange_code(s.spotify_client_id, code, s.spotify_redirect_uri, verifier)

    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get("https://api.spotify.com/v1/me",
                        headers={"Authorization": f"Bearer {tokens['access_token']}"})
        r.raise_for_status()
        me = r.json()

    refresh = tokens.get("refresh_token")
    await get_db()["users"].update_one(
        {"_id": me["id"]},
        {"$set": {
            "display_name": me.get("display_name"),
            "refresh_token_enc": encrypt(refresh) if refresh else None,  # cifrado en reposo
        }},
        upsert=True,
    )
    return {"user_id": me["id"], "display_name": me.get("display_name")}
