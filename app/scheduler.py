"""Scheduler (APScheduler) para tareas periódicas: refresco del user_stats_cache.

Sustituye a los Triggers de Atlas (no disponibles en Mongo local). Se arranca/para
desde el lifespan de FastAPI.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

from app.db.client import get_db
from app.enrich.audio import ReccoBeatsClient
from app.enrich.embeddings import get_embedder
from app.enrich.features import enrich_user_tracks
from app.enrich.lyrics import LyricsClient
from app.ingest.stats import rebuild_user_stats

log = logging.getLogger(__name__)

REFRESH_JOB_ID = "refresh_stats"
ENRICH_JOB_ID = "enrich_features"


async def refresh_all_stats() -> None:
    """Recalcula el cache de stats de todos los usuarios conocidos."""
    db = get_db()
    async for user in db["users"].find({}, {"_id": 1}):
        try:
            await rebuild_user_stats(db, user["_id"])
        except Exception:
            log.exception("Fallo refrescando stats de %s", user.get("_id"))


async def enrich_features_job() -> None:
    """Puebla audio (ReccoBeats) + lyrics de los tracks que aún no lo tengan → activa
    el score por ritmo/letra. Batch acotado; corre periódico en background."""
    db = get_db()
    recco = ReccoBeatsClient()
    lyrics = LyricsClient()
    try:
        res = await enrich_user_tracks(db, recco=recco, lyrics_client=lyrics,
                                       embedder=get_embedder(), limit=40)
        log.info("enrich_features_job: %s", res)
    except Exception:
        log.exception("Fallo en enrich_features_job")
    finally:
        await recco.aclose()
        await lyrics.aclose()


def build_scheduler(interval_hours: int = 6) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(refresh_all_stats, "interval", hours=interval_hours, id=REFRESH_JOB_ID)
    scheduler.add_job(enrich_features_job, "interval", hours=2, id=ENRICH_JOB_ID)
    return scheduler
