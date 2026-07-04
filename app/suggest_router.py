"""Sugerencias de 'vibe' (chips) generadas por DeepSeek, PERSONALIZADAS con el gusto
del usuario (BD) y CACHEADAS 20 min → no se gasta dinero en cada visita.

Se regeneran como MUCHO una vez cada 20 minutos: la primera visita tras expirar el
cache dispara UNA completion; el resto de visitas reusan el cache (coste 0).
"""
import contextlib
import time

from fastapi import APIRouter

from app.agent.llm import DeepSeekClient
from app.config import get_settings
from app.db.client import get_db
from app.preferences import get_preferences
from app.spotify.session import current_user

router = APIRouter(tags=["suggestions"])

_CACHE: dict = {"chips": None, "ts": 0.0}
_TTL = 20 * 60  # segundos — regenera como mucho cada 20 min (control de coste)

_DEFAULTS = [
    "algo oscuro de trap latino para programar de noche",
    "reggaeton underground para el gym",
    "perreo experimental para una fiesta rara",
    "algo chill y melancólico para cuando llueve",
]

_BASE_PROMPT = (
    "Genera EXACTAMENTE 4 sugerencias cortas y variadas de 'vibe' para pedirle a un DJ una "
    "playlist. En español, tono desenfadado, con rollo underground/anti-comercial, cada una de "
    "menos de 60 caracteres. Devuelve SOLO las 4 frases, una por línea, sin números, comillas ni viñetas."
)


async def _taste_context(db) -> str:
    """Resumen breve del gusto del usuario (desde la BD) para personalizar los chips."""
    user = await current_user(db)
    if not user:
        return ""
    parts: list[str] = []
    stats = await db["user_stats_cache"].find_one({"_id": user["_id"]})
    if stats:
        arts = [a.get("artist") for a in (stats.get("top_artists") or [])[:6] if a.get("artist")]
        if arts:
            parts.append("artistas que escucha: " + ", ".join(arts))
    prefs = await get_preferences(db, user["_id"])
    if prefs.get("loved_tags"):
        parts.append("géneros que le molan: " + ", ".join(prefs["loved_tags"][:6]))
    parts.append(f"nivel underground {prefs.get('underground_level', 50)}/100")
    return " · ".join(parts)


async def _generate() -> list[str] | None:
    s = get_settings()
    if not s.deepseek_api_key:
        return None
    ctx = await _taste_context(get_db())
    prompt = _BASE_PROMPT
    if ctx:
        prompt = f"Contexto del usuario — {ctx}. Personaliza a ESE gusto. " + _BASE_PROMPT
    llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
    chips = None
    with contextlib.suppress(Exception):
        res = await llm.chat([{"role": "user", "content": prompt}])
        lines = [ln.strip(" -•\t\"'·") for ln in (res.content or "").splitlines() if ln.strip()]
        chips = [ln for ln in lines if 3 < len(ln) < 90][:4]
    await llm.aclose()
    return chips or None


@router.get("/suggestions")
async def suggestions():
    """4 chips personalizados; se regeneran como MUCHO cada 20 min (cache de coste)."""
    now = time.time()
    if _CACHE["chips"] and (now - _CACHE["ts"] < _TTL):
        return {"chips": _CACHE["chips"], "cached": True}
    _CACHE["chips"] = (await _generate()) or _CACHE["chips"] or _DEFAULTS
    _CACHE["ts"] = now
    return {"chips": _CACHE["chips"], "cached": False}
