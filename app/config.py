"""Configuración central (pydantic-settings, lee .env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017/?directConnection=true"
    mongo_db: str = "vibesync"

    # DeepSeek (OpenAI-compatible)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    # Enriquecimiento
    lastfm_api_key: str = ""
    musicbrainz_user_agent: str = "vibesync/0.1"

    # Spotify
    spotify_client_id: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8000/auth/callback"

    # Seguridad
    fernet_key: str = ""

    # Embeddings
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    use_real_embeddings: bool = False  # False → FakeEmbedder (sin torch); True → BGE-M3

    # Ingesta
    min_ms_played: int = 30_000  # filtro estricto: descarta reproducciones < 30s


@lru_cache
def get_settings() -> Settings:
    return Settings()
