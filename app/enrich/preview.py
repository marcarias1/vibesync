"""Preview de audio (30s) por artista+título.

Spotify `preview_url` está MUERTO para apps nuevas → usamos **Deezer** (primario,
MP3 30s) con fallback a **iTunes** (M4A 30s). Ambos gratis y sin auth. Se resuelve
AL VUELO (las URLs de Deezer están firmadas y caducan → no se cachean). El JSON se
pide desde el backend (evita CORS); el audio suena directo en el `<audio>` del navegador.
"""
import contextlib

import httpx

_DEEZER = "https://api.deezer.com/search"
_ITUNES = "https://itunes.apple.com/search"


async def resolve_preview(artist: str, title: str) -> dict | None:
    """Devuelve {preview_url, source} o None. Deezer primero, iTunes de reserva."""
    artist = (artist or "").strip()
    title = (title or "").strip()
    if not (artist or title):
        return None
    async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "VibeSync/1.0"}) as client:
        # 1) Deezer — búsqueda precisa por campos
        with contextlib.suppress(Exception):
            q = f'artist:"{artist}" track:"{title}"' if artist and title else f"{artist} {title}".strip()
            r = await client.get(_DEEZER, params={"q": q})
            for item in (r.json() or {}).get("data") or []:
                if item.get("preview"):
                    return {"preview_url": item["preview"], "source": "deezer"}
        # 2) iTunes — fallback
        with contextlib.suppress(Exception):
            r = await client.get(_ITUNES, params={
                "term": f"{artist} {title}".strip(), "entity": "song", "limit": 1, "country": "ES"})
            results = (r.json() or {}).get("results") or []
            if results and results[0].get("previewUrl"):
                return {"preview_url": results[0]["previewUrl"], "source": "itunes"}
    return None
