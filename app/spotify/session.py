"""Obtención de un access token fresco a partir del refresh token cifrado."""
from app.config import get_settings
from app.security.crypto import decrypt
from app.spotify.auth import refresh_token


async def get_access_token(db, user_id: str) -> str | None:
    """Descifra el refresh token del usuario y pide un access token nuevo."""
    user = await db["users"].find_one({"_id": user_id})
    if not user or not user.get("refresh_token_enc"):
        return None
    refresh = decrypt(user["refresh_token_enc"])
    tokens = await refresh_token(get_settings().spotify_client_id, refresh)
    return tokens.get("access_token")


async def current_user(db):
    """Devuelve el (único) usuario conectado, o None."""
    return await db["users"].find_one({}, sort=[("_id", 1)])
