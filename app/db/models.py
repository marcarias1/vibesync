"""Modelos Pydantic v2 = esquema de las colecciones MongoDB.

Nota de diseño: `playback_history` es una colección REGULAR (no time-series).
Motivo: la idempotencia del importador exige un índice UNIQUE sobre un `_id`
determinista, y las colecciones time-series de MongoDB no admiten índices unique.
Para un histórico de un usuario (decenas de miles de docs) los índices compuestos
dan casi todo el rendimiento de consulta temporal sin perder la idempotencia.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MongoModel(BaseModel):
    # populate_by_name → poder construir con `id=` o con el alias `_id`.
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


# --------------------------------------------------------------------------- #
class User(MongoModel):
    id: str = Field(alias="_id")                 # spotify user id
    display_name: str | None = None
    refresh_token_enc: str | None = None         # cifrado con Fernet (nunca en claro)
    lastfm_user: str | None = None
    created_at: datetime | None = None


# --------------------------------------------------------------------------- #
class Artist(MongoModel):
    id: str = Field(alias="_id")                 # spotify artist id o mbid
    name: str
    mbid: str | None = None
    tags: list[str] = Field(default_factory=list)        # tags Last.fm normalizados
    genres: list[str] = Field(default_factory=list)      # MusicBrainz / fallback
    lastfm_listeners: int | None = None
    lastfm_playcount: int | None = None
    commerciality_score: float | None = None    # log(listeners) normalizado 0-100
    embedding: list[float] | None = None         # BGE-M3 del perfil textual
    updated_at: datetime | None = None


# --------------------------------------------------------------------------- #
class Track(MongoModel):
    id: str = Field(alias="_id")                 # spotify track id
    uri: str                                     # spotify:track:...
    name: str
    artist_id: str | None = None
    artist_name: str | None = None
    mbid: str | None = None
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None
    custom_tags: dict | None = None              # mood/bailable → POSPUESTO (nullable)
    updated_at: datetime | None = None


# --------------------------------------------------------------------------- #
class PlaybackEvent(MongoModel):
    id: str = Field(alias="_id")                 # determinista → idempotencia
    user_id: str
    track_uri: str
    ts: datetime
    ms_played: int
    reason_start: str | None = None
    reason_end: str | None = None
    shuffle: bool | None = None
    skipped: bool | None = None
    platform: str | None = None
    track_name: str | None = None
    artist_name: str | None = None

    @staticmethod
    def make_id(user_id: str, track_uri: str, ts: datetime) -> str:
        """Clave compuesta determinista (sin hash: legible y sin colisiones)."""
        return f"{user_id}:{track_uri}:{ts.isoformat()}"


# --------------------------------------------------------------------------- #
class UserTrackVibe(MongoModel):
    id: str = Field(alias="_id")                 # f"{user_id}:{track_uri}"
    user_id: str
    track_uri: str
    play_count: int = 0
    total_ms: int = 0
    last_played: datetime | None = None


# --------------------------------------------------------------------------- #
class DraftTrack(MongoModel):
    artist: str
    title: str
    uri: str | None = None
    reason: str | None = None
    cover_url: str | None = None
    score: float | None = None


class PlaylistDraft(MongoModel):
    id: str = Field(alias="_id")                 # uuid
    user_id: str
    prompt: str | None = None
    name: str
    status: str = "draft"                        # draft | published
    tracks: list[DraftTrack] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)
    spotify_playlist_id: str | None = None
    url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --------------------------------------------------------------------------- #
def _default_weights() -> dict:
    return {"content": 0.35, "lyrics": 0.15, "audio": 0.20, "tags": 0.20, "underground": 0.10}


class UserPreferences(MongoModel):
    id: str = Field(alias="_id")                 # user_id
    blocked_artists: list[str] = Field(default_factory=list)      # veto duro
    disliked_artists: dict[str, float] = Field(default_factory=dict)  # artista -> peso (bloqueo ligero)
    disliked_tags: dict[str, float] = Field(default_factory=dict)
    loved_artists: list[str] = Field(default_factory=list)
    loved_tags: list[str] = Field(default_factory=list)
    underground_level: int = 50                  # 0-100 (sesga la ventana de comercialidad)
    content_centroid: list[float] | None = None  # media de embeddings de temas gustados
    lyrics_centroid: list[float] | None = None
    audio_profile: dict | None = None            # medias {tempo,energy,danceability,valence}
    weights: dict = Field(default_factory=_default_weights)
    updated_at: datetime | None = None


class Feedback(MongoModel):
    id: str = Field(alias="_id")                 # f"{user_id}:{track_uri}"
    user_id: str
    track_uri: str | None = None
    artist: str | None = None
    verdict: str                                 # like | dislike | remove | block
    context: str | None = None
    ts: datetime | None = None
