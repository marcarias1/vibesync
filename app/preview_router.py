"""Endpoint de preview de audio (30s). Proxea la búsqueda (Deezer→iTunes); el audio
lo reproduce el navegador directamente en un <audio>."""
from fastapi import APIRouter

from app.enrich.preview import resolve_preview

router = APIRouter(tags=["preview"])


@router.get("/preview")
async def preview(artist: str = "", title: str = ""):
    return await resolve_preview(artist, title) or {"preview_url": None, "source": None}
