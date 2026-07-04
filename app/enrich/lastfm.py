"""Cliente Last.fm (gratis). Proxy de comercialidad (listeners) + tags + similares + bio."""
import re

import httpx

_HTML = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Quita etiquetas HTML y el pie 'Read more on Last.fm' del bio."""
    text = _HTML.sub("", text or "").split("Read more on Last.fm")[0]
    return " ".join(text.split()).strip()


class LastFmClient:
    BASE = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.client = client or httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _get(self, method: str, **params) -> dict:
        q = {"method": method, "api_key": self.api_key, "format": "json", **params}
        r = await self.client.get(self.BASE, params=q)
        r.raise_for_status()
        return r.json()

    async def artist_info(self, artist: str) -> dict:
        a = (await self._get("artist.getinfo", artist=artist)).get("artist", {})
        stats = a.get("stats", {})
        return {
            "name": a.get("name"),
            "mbid": a.get("mbid") or None,
            "listeners": int(stats.get("listeners", 0) or 0),
            "playcount": int(stats.get("playcount", 0) or 0),
            "tags": [t["name"] for t in a.get("tags", {}).get("tag", [])],
            "bio": _strip_html((a.get("bio") or {}).get("summary", ""))[:500],
        }

    async def similar_artists(self, artist: str, limit: int = 20) -> list[str]:
        data = await self._get("artist.getsimilar", artist=artist, limit=limit)
        return [s["name"] for s in data.get("similarartists", {}).get("artist", [])]

    async def top_tags(self, artist: str) -> list[str]:
        data = await self._get("artist.gettoptags", artist=artist)
        return [t["name"] for t in data.get("toptags", {}).get("tag", [])]

    async def top_tracks(self, artist: str, limit: int = 3) -> list[dict]:
        data = await self._get("artist.gettoptracks", artist=artist, limit=limit)
        tracks = data.get("toptracks", {}).get("track", [])
        return [{"artist": artist, "name": t["name"]} for t in tracks[:limit]]

    async def clean_tags(self, artist: str, min_count: int = 10, limit: int = 10) -> list[str]:
        """Tags de calidad: gettoptags con recuento (0-100); filtra ruido (count bajo)."""
        data = await self._get("artist.gettoptags", artist=artist)
        tags = data.get("toptags", {}).get("tag", [])
        kept = [t["name"] for t in tags if int(t.get("count", 0) or 0) >= min_count]
        return (kept or [t["name"] for t in tags])[:limit]
