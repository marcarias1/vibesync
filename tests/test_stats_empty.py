"""rebuild_user_stats sobre un usuario sin histórico: no peta, totales a 0."""
from app.ingest.stats import rebuild_user_stats


async def test_rebuild_usuario_sin_datos(db):
    # Limpiamos la caché (la fixture db no toca user_stats_cache).
    await db["user_stats_cache"].delete_many({})

    doc = await rebuild_user_stats(db, "sin_datos")

    assert doc["total_plays"] == 0
    assert doc["distinct_tracks"] == 0
    assert doc["top_tracks"] == []
    assert doc["top_artists"] == []
    # Patrones densos, todo a cero.
    assert doc["hourly_pattern"] == [0] * 24
    assert doc["weekday_pattern"] == [0] * 7
