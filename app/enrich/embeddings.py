"""Embeddings pluggables.

- FakeEmbedder: determinista, sin dependencias pesadas (dev/tests).
- BGEEmbedder: BGE-M3 real (lazy import de sentence-transformers; extra 'ml').
"""
import hashlib
import math
from typing import Protocol

from app.config import get_settings


class Embedder(Protocol):
    dim: int

    def encode(self, text: str) -> list[float]: ...


class FakeEmbedder:
    """Vector determinista y normalizado derivado del texto (sin torch)."""

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def encode(self, text: str) -> list[float]:
        vals: list[float] = []
        i = 0
        while len(vals) < self.dim:
            digest = hashlib.sha256(f"{i}:{text}".encode()).digest()
            for b in digest:
                vals.append((b - 127.5) / 127.5)
                if len(vals) >= self.dim:
                    break
            i += 1
        norm = math.sqrt(sum(v * v for v in vals)) or 1.0
        return [v / norm for v in vals]


class BGEEmbedder:
    """BGE-M3 real. Carga perezosa para no importar torch salvo que se use."""

    def __init__(self, model_name: str = "BAAI/bge-m3", dim: int = 1024) -> None:
        self.model_name = model_name
        self.dim = dim
        self._model = None

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, text: str) -> list[float]:
        vec = self._ensure().encode(text, normalize_embeddings=True)
        return vec.tolist()


def artist_profile_text(name: str, tags: list[str], genres: list[str], bio: str | None = None) -> str:
    """Perfil textual para el embedding: nombre + tags + géneros + bio descriptiva.
    La bio (prosa real de Last.fm) hace el embedding mucho más discriminativo."""
    parts = [name, ", ".join(tags), ", ".join(genres)]
    if bio:
        parts.append(bio)
    return " — ".join(p for p in parts if p)


def get_embedder() -> Embedder:
    s = get_settings()
    if s.use_real_embeddings:
        return BGEEmbedder(s.embedding_model, s.embedding_dim)
    return FakeEmbedder(s.embedding_dim)
