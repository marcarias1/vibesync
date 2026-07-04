"""Esquema del 'Extended Streaming History' de Spotify (Streaming_History_Audio_*.json).

Solo declaramos los campos que usamos; `extra="ignore"` descarta el resto.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RawStreamEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ts: datetime
    ms_played: int
    spotify_track_uri: str | None = None
    master_metadata_track_name: str | None = None
    master_metadata_album_artist_name: str | None = None
    reason_start: str | None = None
    reason_end: str | None = None
    shuffle: bool | None = None
    skipped: bool | None = None
    platform: str | None = None


class ImportResult(BaseModel):
    total: int          # registros en el fichero
    kept: int           # tras el filtro de calidad
    inserted: int       # nuevos insertados
    duplicates: int     # ya existentes (idempotencia)
