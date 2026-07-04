"""Creación idempotente de índices (regulares + vectorial).

Se llama en el arranque de la app (lifespan). `create_index` y
`create_search_index` son idempotentes: no fallan si el índice ya existe.
"""
import logging

from pymongo import ASCENDING, DESCENDING
from pymongo.operations import SearchIndexModel

from app.config import get_settings

log = logging.getLogger(__name__)


async def ensure_indexes(db) -> None:
    # --- playback_history (colección regular; _id determinista ya es unique) ---
    ph = db["playback_history"]
    await ph.create_index([("user_id", ASCENDING), ("ts", DESCENDING)])
    await ph.create_index([("user_id", ASCENDING), ("track_uri", ASCENDING)])

    # --- user_tracks_vibe ---
    await db["user_tracks_vibe"].create_index(
        [("user_id", ASCENDING), ("play_count", DESCENDING)]
    )

    # --- borradores/historial de playlists + feedback ---
    await db["playlist_drafts"].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    await db["feedback"].create_index([("user_id", ASCENDING), ("verdict", ASCENDING)])

    # --- artists / tracks ---
    await db["artists"].create_index([("name", ASCENDING)])
    await db["artists"].create_index([("commerciality_score", ASCENDING)])
    await db["tracks"].create_index([("artist_id", ASCENDING)])
    await db["tracks"].create_index([("uri", ASCENDING)], unique=True)

    await _ensure_vector_index(db)


async def _ensure_vector_index(db) -> None:
    """Índice vectorial sobre tracks.embedding (requiere mongot / Atlas local)."""
    dim = get_settings().embedding_dim
    model = SearchIndexModel(
        name="vec_tracks",
        type="vectorSearch",
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": dim,
                    "similarity": "cosine",
                }
            ]
        },
    )
    try:
        await db["tracks"].create_search_index(model)
        log.info("Índice vectorial 'vec_tracks' creado.")
    except Exception as exc:
        # Ya existe, o el mongod no tiene mongot (sin vector search). No es fatal.
        log.info("Índice vectorial no creado (ya existe o mongod sin mongot): %s", exc)
