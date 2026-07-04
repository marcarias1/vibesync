"""Letras (lyrics.ovh, gratis, sin clave) + embedding de la letra para el score."""
import urllib.parse

import httpx

from app.enrich.embeddings import get_embedder


class LyricsClient:
    BASE = "https://api.lyrics.ovh/v1"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def fetch(self, artist: str, title: str) -> str | None:
        url = f"{self.BASE}/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"
        r = await self.client.get(url)
        if r.status_code != 200:
            return None
        return (r.json() or {}).get("lyrics") or None


def embed_lyrics(text: str, embedder=None) -> list[float]:
    """Embedding de la letra (recortada) — captura tema/mood para el scoring."""
    embedder = embedder or get_embedder()
    return embedder.encode(text[:2000])
