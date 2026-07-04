"""Scheduler (APScheduler) para tareas periódicas: refresco del user_stats_cache.

Sustituye a los Triggers de Atlas (no disponibles en Mongo local). Se arranca/para
desde el lifespan de FastAPI.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

from app.db.client import get_db
from app.ingest.stats import rebuild_user_stats

log = logging.getLogger(__name__)

REFRESH_JOB_ID = "refresh_stats"


async def refresh_all_stats() -> None:
    """Recalcula el cache de stats de todos los usuarios conocidos."""
    db = get_db()
    async for user in db["users"].find({}, {"_id": 1}):
        try:
            await rebuild_user_stats(db, user["_id"])
        except Exception:
            log.exception("Fallo refrescando stats de %s", user.get("_id"))


def build_scheduler(interval_hours: int = 6) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(refresh_all_stats, "interval", hours=interval_hours, id=REFRESH_JOB_ID)
    return scheduler
