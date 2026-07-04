"""Sugerencias de 'vibe' (chips) generadas por DeepSeek al arrancar el servicio.

Se generan una vez por proceso (cache en memoria) → frescas en cada reinicio.
Si no hay clave o falla, cae en unos valores por defecto.
"""
import contextlib

from fastapi import APIRouter

from app.agent.llm import DeepSeekClient
from app.config import get_settings

router = APIRouter(tags=["suggestions"])

_CACHE: dict = {"chips": None}

_DEFAULTS = [
    "algo oscuro de trap latino para programar de noche",
    "reggaeton underground para el gym",
    "perreo experimental para una fiesta rara",
    "algo chill y melancólico para cuando llueve",
]

_PROMPT = (
    "Genera EXACTAMENTE 4 sugerencias cortas y variadas de 'vibe' para pedirle a un DJ una "
    "playlist. En español, tono desenfadado, con rollo underground/anti-comercial, cada una de "
    "menos de 60 caracteres. Devuelve SOLO las 4 frases, una por línea, sin números, comillas ni viñetas."
)


@router.get("/suggestions")
async def suggestions():
    """Devuelve 4 chips de vibe; las genera DeepSeek en la primera llamada tras arrancar."""
    if _CACHE["chips"]:
        return {"chips": _CACHE["chips"]}
    s = get_settings()
    chips = None
    if s.deepseek_api_key:
        llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
        with contextlib.suppress(Exception):
            res = await llm.chat([{"role": "user", "content": _PROMPT}])
            lines = [ln.strip(" -•\t\"'·") for ln in (res.content or "").splitlines() if ln.strip()]
            chips = [ln for ln in lines if 3 < len(ln) < 90][:4]
        await llm.aclose()
    _CACHE["chips"] = chips or _DEFAULTS
    return {"chips": _CACHE["chips"]}
