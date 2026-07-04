"""Cliente MusicBrainz (gratis, 1 req/s, User-Agent obligatorio). IDs + géneros."""
import httpx


class MusicBrainzClient:
    BASE = "https://musicbrainz.org/ws/2"

    def __init__(self, user_agent: str, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(
            timeout=10.0, headers={"User-Agent": user_agent}
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def search_artist(self, name: str) -> dict | None:
        r = await self.client.get(
            f"{self.BASE}/artist", params={"query": name, "fmt": "json", "limit": 1}
        )
        r.raise_for_status()
        arts = r.json().get("artists", [])
        if not arts:
            return None
        a = arts[0]
        return {
            "mbid": a.get("id"),
            "name": a.get("name"),
            "genres": [g["name"] for g in a.get("genres", [])],
        }
