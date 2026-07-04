"""Definición de Agent Tools: modelos Pydantic de argumentos + $match seguro + schemas.

El LLM rellena estos argumentos → hay que blindar el `$match` contra NoSQL injection:
tipos estrictos, rechazo de strings con operadores ('$...') y regex escapado.
"""
import re

from pydantic import BaseModel, Field, field_validator, model_validator

# Permite letras (con acentos), dígitos, espacios y signos musicales típicos.
_SAFE_TEXT = re.compile(r"^[\w\s\-&'./()áéíóúüñÁÉÍÓÚÜÑ]+$", re.UNICODE)


def _safe_text(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if v.startswith("$") or not _SAFE_TEXT.match(v):
        raise ValueError(f"valor de búsqueda no permitido: {v!r}")
    return v


class SearchTracksArgs(BaseModel):
    artist_name: str | None = None
    genre: str | None = None
    tag: str | None = None
    min_plays: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)

    @field_validator("artist_name", "genre", "tag")
    @classmethod
    def _validate_text(cls, v):
        return _safe_text(v)


class SemanticSearchArgs(BaseModel):
    vibe_query: str = Field(..., min_length=1, max_length=300)
    limit: int = Field(20, ge=1, le=100)


class SimilarUndergroundArgs(BaseModel):
    source_artist: str = Field(..., min_length=1)
    limit: int = Field(20, ge=1, le=100)


class UserProfileArgs(BaseModel):
    time_range: str = Field("long_term")

    @field_validator("time_range")
    @classmethod
    def _tr(cls, v):
        if v not in {"short_term", "medium_term", "long_term"}:
            raise ValueError("time_range inválido")
        return v


class PlaylistControllerArgs(BaseModel):
    playlist_name: str = Field(..., min_length=1, max_length=100)
    track_uris: list[str] = Field(..., min_length=1)
    mode: str = Field("create")

    @field_validator("mode")
    @classmethod
    def _mode(cls, v):
        if v not in {"create", "overwrite"}:
            raise ValueError("mode debe ser create|overwrite")
        return v

    @field_validator("track_uris")
    @classmethod
    def _uris(cls, v):
        for u in v:
            if not u.startswith("spotify:track:"):
                raise ValueError(f"URI inválida: {u!r}")
        return v


class TrackRef(BaseModel):
    artist: str = ""
    title: str = ""

    @model_validator(mode="after")
    def _al_menos_uno(self):
        if not (self.artist.strip() or self.title.strip()):
            raise ValueError("indica al menos artista o título")
        return self


class CreatePlaylistArgs(BaseModel):
    playlist_name: str = Field(..., min_length=1, max_length=100)
    tracks: list[TrackRef] = Field(..., min_length=1, max_length=50)


def build_match(args: SearchTracksArgs) -> dict:
    """Construye un $match SOLO con campos whitelisted; regex escapado."""
    m: dict = {}
    if args.artist_name:
        m["artist_name"] = {"$regex": re.escape(args.artist_name), "$options": "i"}
    tags = [t.lower() for t in (args.genre, args.tag) if t]
    if tags:
        m["tags"] = {"$in": tags}
    if args.min_plays > 0:
        m["play_count"] = {"$gte": args.min_plays}   # denormalizado en tracks
    return m


# --- Schemas en formato OpenAI/function-calling para DeepSeek --------------- #
def _fn(name, desc, params):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": params}}


TOOL_SCHEMAS = [
    _fn("get_user_music_profile", "Perfil musical del usuario (tops, patrones horarios).",
        {"type": "object", "properties": {
            "time_range": {"type": "string", "enum": ["short_term", "medium_term", "long_term"]}}}),
    _fn("search_tracks_database", "Busca tracks en la BD local por artista/género/tag.",
        {"type": "object", "properties": {
            "artist_name": {"type": "string"}, "genre": {"type": "string"},
            "tag": {"type": "string"}, "min_plays": {"type": "integer"},
            "limit": {"type": "integer"}}}),
    _fn("find_similar_underground_tracks", "Similares a un artista aplicando filtro anti-comerciales.",
        {"type": "object", "properties": {
            "source_artist": {"type": "string"}, "limit": {"type": "integer"}},
         "required": ["source_artist"]}),
    _fn("semantic_track_search", "Búsqueda por 'vibe' en lenguaje natural (vector search).",
        {"type": "object", "properties": {
            "vibe_query": {"type": "string"}, "limit": {"type": "integer"}},
         "required": ["vibe_query"]}),
    _fn("get_temporal_context", "Hora y día actuales.", {"type": "object", "properties": {}}),
    _fn("get_user_preferences",
        "Preferencias del usuario: nivel underground, artistas amados y VETADOS (no los propongas).",
        {"type": "object", "properties": {}}),
    _fn("spotify_playlist_controller", "Crea o sobrescribe una playlist en Spotify.",
        {"type": "object", "properties": {
            "playlist_name": {"type": "string"},
            "track_uris": {"type": "array", "items": {"type": "string"}},
            "mode": {"type": "string", "enum": ["create", "overwrite"]}},
         "required": ["playlist_name", "track_uris"]}),
    _fn("crear_playlist_spotify",
        "Resuelve los temas (artista+título) en Spotify y CREA la playlist real en la cuenta del usuario.",
        {"type": "object", "properties": {
            "playlist_name": {"type": "string"},
            "tracks": {"type": "array", "items": {"type": "object", "properties": {
                "artist": {"type": "string"}, "title": {"type": "string"}},
                "required": ["artist", "title"]}}},
         "required": ["playlist_name", "tracks"]}),
    _fn("proponer_playlist_draft",
        "Propone un BORRADOR de playlist (artista+título) SIN crear nada en Spotify; el usuario lo revisará y editará antes de confirmar.",
        {"type": "object", "properties": {
            "playlist_name": {"type": "string"},
            "tracks": {"type": "array", "items": {"type": "object", "properties": {
                "artist": {"type": "string"}, "title": {"type": "string"}},
                "required": ["artist", "title"]}}},
         "required": ["playlist_name", "tracks"]}),
]

ARG_MODELS: dict[str, type[BaseModel]] = {
    "get_user_music_profile": UserProfileArgs,
    "search_tracks_database": SearchTracksArgs,
    "find_similar_underground_tracks": SimilarUndergroundArgs,
    "semantic_track_search": SemanticSearchArgs,
    "spotify_playlist_controller": PlaylistControllerArgs,
    "crear_playlist_spotify": CreatePlaylistArgs,
    "proponer_playlist_draft": CreatePlaylistArgs,
}
