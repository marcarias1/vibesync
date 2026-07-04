"""Cliente ReccoBeats (gratis): audio features (ritmo/energía) — sustituto del
Audio Features de Spotify (muerto). Se consulta por Spotify track id."""
import httpx


class ReccoBeatsClient:
    BASE = "https://api.reccobeats.com/v1"
    KEYS = ("tempo", "energy", "danceability", "valence", "acousticness", "loudness")

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def audio_features(self, spotify_track_id: str) -> dict | None:
        """Flujo de 2 pasos: resolver el Spotify id al id interno de ReccoBeats y
        luego pedir sus audio features. Devuelve {tempo,energy,danceability,valence,...}."""
        r = await self.client.get(f"{self.BASE}/track", params={"ids": spotify_track_id})
        if r.status_code != 200:
            return None
        content = (r.json() or {}).get("content") or []
        rid = content[0].get("id") if content else None
        if not rid:
            return None
        r2 = await self.client.get(f"{self.BASE}/track/{rid}/audio-features")
        if r2.status_code != 200:
            return None
        feats = r2.json() or {}
        return {k: feats[k] for k in self.KEYS if k in feats} or None
