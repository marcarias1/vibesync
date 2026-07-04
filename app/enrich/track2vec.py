"""Embeddings COLABORATIVOS (track2vec): Word2Vec sobre sesiones de escucha.

Cada sesión (secuencia de `track_uri` separada por huecos temporales) es una
"frase"; los tracks que se escuchan juntos acaban cerca en el espacio vectorial.
Señal complementaria a los embeddings de CONTENIDO (BGE-M3): captura "qué suena
junto" en vez de "de qué va la canción". Fuerte cuando hay volumen de histórico.
"""
from datetime import timedelta

from gensim.models import Word2Vec  # type: ignore[import-untyped]


async def build_sessions(db, user_id: str, gap_minutes: int = 30) -> list[list[str]]:
    """Parte el histórico en sesiones cortando donde hay un hueco > gap_minutes."""
    cursor = db["playback_history"].find(
        {"user_id": user_id}, {"track_uri": 1, "ts": 1, "_id": 0}).sort("ts", 1)
    events = await cursor.to_list(None)

    sessions: list[list[str]] = []
    current: list[str] = []
    last = None
    gap = timedelta(minutes=gap_minutes)
    for e in events:
        ts = e["ts"]
        if last is not None and ts - last > gap and current:
            sessions.append(current)
            current = []
        current.append(e["track_uri"])
        last = ts
    if current:
        sessions.append(current)
    return sessions


def train_track2vec(sessions: list[list[str]], *, dim: int = 64, window: int = 5,
                    min_count: int = 2, epochs: int = 30, seed: int = 1) -> Word2Vec:
    """Entrena skip-gram (sg=1) sobre las sesiones. workers=1 para reproducibilidad."""
    return Word2Vec(sentences=sessions, vector_size=dim, window=window,
                    min_count=min_count, workers=1, seed=seed, epochs=epochs, sg=1)


def similar_tracks(model: Word2Vec, uri: str, topn: int = 10) -> list[tuple[str, float]]:
    if uri not in model.wv:
        return []
    return model.wv.most_similar(uri, topn=topn)
