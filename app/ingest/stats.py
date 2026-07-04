"""Precálculo de estadísticas del usuario a partir de `playback_history`.

Objetivo: generar un doc COMPACTO en `user_stats_cache` (uno por usuario) que
resuma su histórico de escucha, para inyectarlo como contexto al LLM sin gastar
tokens recorriendo miles de reproducciones crudas.
"""
from datetime import datetime, timezone


async def rebuild_user_stats(db, user_id: str) -> dict:
    """Agrega el histórico del usuario y hace upsert del resumen en caché.

    Una única agregación con $facet calcula todas las vistas en una pasada:
    top tracks/artistas, patrón horario y semanal, y totales. Devuelve el doc
    guardado (con _id=user_id y generated_at).
    """
    pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$facet": {
                # Top 20 tracks por nº de reproducciones (group por track_uri).
                "top_tracks": [
                    {
                        "$group": {
                            "_id": "$track_uri",
                            "plays": {"$sum": 1},
                            # nombre/artista: primer valor no nulo observado.
                            "name": {"$first": "$track_name"},
                            "artist": {"$first": "$artist_name"},
                        }
                    },
                    {"$sort": {"plays": -1, "_id": 1}},
                    {"$limit": 20},
                    {
                        "$project": {
                            "_id": 0,
                            "track_uri": "$_id",
                            "name": 1,
                            "artist": 1,
                            "plays": 1,
                        }
                    },
                ],
                # Top 20 artistas por nº de reproducciones (group por artist_name).
                "top_artists": [
                    {"$match": {"artist_name": {"$ne": None}}},
                    {"$group": {"_id": "$artist_name", "plays": {"$sum": 1}}},
                    {"$sort": {"plays": -1, "_id": 1}},
                    {"$limit": 20},
                    {"$project": {"_id": 0, "artist": "$_id", "plays": 1}},
                ],
                # Recuento por hora del día (0-23).
                "hourly": [
                    {"$group": {"_id": {"$hour": "$ts"}, "plays": {"$sum": 1}}},
                ],
                # Recuento por día de la semana ($dayOfWeek: 1=domingo .. 7=sábado).
                "weekday": [
                    {"$group": {"_id": {"$dayOfWeek": "$ts"}, "plays": {"$sum": 1}}},
                ],
                # Totales.
                "totals": [
                    {
                        "$group": {
                            "_id": None,
                            "total_plays": {"$sum": 1},
                            "tracks": {"$addToSet": "$track_uri"},
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "total_plays": 1,
                            "distinct_tracks": {"$size": "$tracks"},
                        }
                    },
                ],
            }
        },
    ]

    cur = await db["playback_history"].aggregate(pipeline)
    rows = await cur.to_list(None)
    facet = rows[0] if rows else {}

    top_tracks = facet.get("top_tracks", [])
    top_artists = facet.get("top_artists", [])

    # Patrones a listas de 24 / 7 posiciones (índice = hora / día-1) para un
    # doc denso y estable, fácil de leer por el LLM.
    hourly_pattern = [0] * 24
    for r in facet.get("hourly", []):
        hourly_pattern[int(r["_id"])] = r["plays"]

    weekday_pattern = [0] * 7
    for r in facet.get("weekday", []):
        # $dayOfWeek: 1=domingo .. 7=sábado → índice 0..6.
        weekday_pattern[int(r["_id"]) - 1] = r["plays"]

    totals = facet.get("totals", [])
    total_plays = totals[0]["total_plays"] if totals else 0
    distinct_tracks = totals[0]["distinct_tracks"] if totals else 0

    doc = {
        "_id": user_id,
        "generated_at": datetime.now(timezone.utc),
        "top_tracks": top_tracks,
        "top_artists": top_artists,
        "hourly_pattern": hourly_pattern,
        "weekday_pattern": weekday_pattern,
        "total_plays": total_plays,
        "distinct_tracks": distinct_tracks,
    }

    # Upsert por _id=user_id: idempotente, un doc por usuario.
    await db["user_stats_cache"].update_one(
        {"_id": user_id}, {"$set": doc}, upsert=True
    )
    return doc
