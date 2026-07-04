"""Controlador de playlists: creación idempotente + troceo a 100 URIs/request."""
from collections.abc import Iterator

import httpx

API = "https://api.spotify.com/v1"
MAX_URIS_PER_REQUEST = 100


def chunk_uris(uris: list[str], size: int = MAX_URIS_PER_REQUEST) -> Iterator[list[str]]:
    for i in range(0, len(uris), size):
        yield uris[i:i + size]


class SpotifyPlaylistController:
    def __init__(self, access_token: str, db=None, client: httpx.AsyncClient | None = None) -> None:
        self.db = db
        self.client = client or httpx.AsyncClient(timeout=15.0)
        self._headers = {"Authorization": f"Bearer {access_token}"}

    async def aclose(self) -> None:
        await self.client.aclose()

    async def get_or_create(self, user_id: str, name: str) -> str:
        """Reutiliza el playlist_id guardado (Spotify permite nombres duplicados)."""
        if self.db is not None:
            doc = await self.db["playlists"].find_one({"user_id": user_id, "name": name})
            if doc:
                return doc["playlist_id"]
        pid = await self._create(name)
        if self.db is not None:
            await self.db["playlists"].update_one(
                {"user_id": user_id, "name": name},
                {"$set": {"playlist_id": pid}},
                upsert=True,
            )
        return pid

    async def create_new(self, user_id: str, name: str) -> str:
        """Fuerza una playlist NUEVA (mode='create') y guarda el mapping."""
        pid = await self._create(name)
        if self.db is not None:
            await self.db["playlists"].update_one(
                {"user_id": user_id, "name": name},
                {"$set": {"playlist_id": pid}},
                upsert=True,
            )
        return pid

    async def _create(self, name: str) -> str:
        r = await self.client.post(f"{API}/me/playlists", json={"name": name}, headers=self._headers)
        r.raise_for_status()
        return r.json()["id"]

    async def set_items(self, playlist_id: str, uris: list[str]) -> None:
        """PUT reemplaza (primeros 100), POST añade el resto en tandas de 100."""
        chunks = list(chunk_uris(uris))
        first = chunks[0] if chunks else []
        r = await self.client.put(
            f"{API}/playlists/{playlist_id}/items", json={"uris": first}, headers=self._headers)
        r.raise_for_status()
        for ch in chunks[1:]:
            r = await self.client.post(
                f"{API}/playlists/{playlist_id}/items", json={"uris": ch}, headers=self._headers)
            r.raise_for_status()

    async def search_track_uri(self, artist: str, title: str) -> str | None:
        """Resuelve 'artista + título' a una URI de Spotify (o None si no existe)."""
        found = await self.search_track(artist, title)
        return found["uri"] if found else None

    async def search_track(self, artist: str, title: str) -> dict | None:
        """Como search_track_uri pero devuelve uri + carátula + nombres (para tarjetas).
        Tolera que falte artista o título (busca con lo que haya)."""
        parts = []
        if title:
            parts.append(f"track:{title}")
        if artist:
            parts.append(f"artist:{artist}")
        q = " ".join(parts) or (title or artist)
        if not q:
            return None
        r = await self.client.get(f"{API}/search", headers=self._headers,
                                  params={"q": q, "type": "track", "limit": 1})
        if r.status_code != 200:
            return None
        items = r.json().get("tracks", {}).get("items", [])
        if not items:
            return None
        t = items[0]
        images = (t.get("album") or {}).get("images") or []
        return {
            "uri": t["uri"],
            "name": t.get("name"),
            "artist": (t.get("artists") or [{}])[0].get("name"),
            "cover_url": images[0]["url"] if images else None,
        }

    async def search_tracks(self, query: str, limit: int = 8) -> list[dict]:
        """Búsqueda en vivo: varios resultados con uri, nombre, artista y carátula."""
        if not query.strip():
            return []
        r = await self.client.get(f"{API}/search", headers=self._headers,
                                  params={"q": query, "type": "track", "limit": limit})
        if r.status_code != 200:
            return []
        out = []
        for t in r.json().get("tracks", {}).get("items", []):
            images = (t.get("album") or {}).get("images") or []
            out.append({
                "uri": t["uri"], "name": t.get("name"),
                "artist": ", ".join(a["name"] for a in t.get("artists", []) if a.get("name")),
                "cover_url": images[-1]["url"] if images else None,  # la miniatura más pequeña
            })
        return out

    async def remove_items(self, playlist_id: str, uris: list[str]) -> None:
        """Quita temas de una playlist ya creada (DELETE en tandas de 100)."""
        for ch in chunk_uris(uris):
            r = await self.client.request(
                "DELETE", f"{API}/playlists/{playlist_id}/tracks",
                json={"tracks": [{"uri": u} for u in ch]}, headers=self._headers)
            r.raise_for_status()
