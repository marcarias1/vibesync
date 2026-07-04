"""Agregaciones que RECALCULAN contadores desde playback_history (fuente de verdad).

Idempotente por diseño: recalcula desde cero con $group + $merge, en vez de $inc
(que doblaría los counts al resubir el fichero).
"""


def _vibe_pipeline(user_id: str) -> list[dict]:
    return [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": {"user_id": "$user_id", "track_uri": "$track_uri"},
                "play_count": {"$sum": 1},
                "total_ms": {"$sum": "$ms_played"},
                "last_played": {"$max": "$ts"},
            }
        },
        {
            "$project": {
                "_id": {"$concat": ["$_id.user_id", ":", "$_id.track_uri"]},
                "user_id": "$_id.user_id",
                "track_uri": "$_id.track_uri",
                "play_count": 1,
                "total_ms": 1,
                "last_played": 1,
            }
        },
        {
            "$merge": {
                "into": "user_tracks_vibe",
                "on": "_id",
                "whenMatched": "replace",
                "whenNotMatched": "insert",
            }
        },
    ]


async def recompute_user_vibe(db, user_id: str) -> None:
    """Ejecuta el pipeline; $merge escribe en user_tracks_vibe server-side."""
    cursor = await db["playback_history"].aggregate(_vibe_pipeline(user_id))
    await cursor.to_list(None)  # hay que agotar el cursor para que $merge se ejecute
