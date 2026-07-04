"""Búsqueda semántica (vector) + Filtro Anti-Comerciales v2."""
from app.enrich.commerciality import jaccard, within_underground_window


def vector_search_pipeline(
    query_vector: list[float],
    limit: int = 20,
    num_candidates: int = 200,
    extra_filter: dict | None = None,
) -> list[dict]:
    stage: dict = {
        "index": "vec_tracks",
        "path": "embedding",
        "queryVector": query_vector,
        "numCandidates": num_candidates,
        "limit": limit,
    }
    if extra_filter:
        stage["filter"] = extra_filter
    return [
        {"$vectorSearch": stage},
        {"$project": {
            "_id": 1, "uri": 1, "name": 1, "artist_name": 1, "tags": 1,
            "score": {"$meta": "vectorSearchScore"}}},
    ]


async def semantic_search(db, embedder, query: str, limit: int = 20) -> list[dict]:
    qv = embedder.encode(query)
    cursor = await db["tracks"].aggregate(vector_search_pipeline(qv, limit))
    return await cursor.to_list(None)


def filter_underground(
    source_score: float,
    candidates: list[dict],
    *,
    source_tags: list[str] | None = None,
    min_jaccard: float = 0.1,
    down: float = 25.0,
    up: float = 8.0,
    blocked: set[str] | None = None,
) -> list[dict]:
    """Aplica la ventana asimétrica de comercialidad + solapamiento de tags,
    excluyendo artistas vetados (`blocked`, en minúsculas)."""
    blocked = blocked or set()
    out: list[dict] = []
    for c in candidates:
        if (c.get("name") or "").lower() in blocked:
            continue
        cand_score = c.get("commerciality_score") or 0.0
        if not within_underground_window(source_score, cand_score, down, up):
            continue
        if source_tags is not None:
            if jaccard(source_tags, c.get("tags", [])) < min_jaccard:
                continue
        out.append(c)
    return out
