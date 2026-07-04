"""Endpoint del importador del histórico GDPR."""
import json

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.db.client import get_db
from app.enrich.embeddings import get_embedder
from app.enrich.tracks import rebuild_tracks
from app.ingest.aggregations import recompute_user_vibe
from app.ingest.importer import ingest
from app.ingest.stats import rebuild_user_stats

router = APIRouter(prefix="/import", tags=["import"])


async def _refresh(db, user_id: str) -> None:
    """Recalcula contadores, cache de stats y (re)construye los tracks buscables."""
    await recompute_user_vibe(db, user_id)
    await rebuild_user_stats(db, user_id)
    await rebuild_tracks(db, user_id, embedder=get_embedder())


@router.post("/streaming-history")
async def import_streaming_history(
    background: BackgroundTasks,
    user_id: str = Form(...),
    files: list[UploadFile] = File(...),
):
    db = get_db()
    raw: list[dict] = []
    for f in files:
        try:
            data = json.loads(await f.read())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(400, f"'{f.filename}' no es JSON válido: {exc}") from exc
        raw.extend(data if isinstance(data, list) else [data])

    result = await ingest(db, user_id, raw)
    # background: recalcula counts + stats cache (no bloquea la respuesta)
    background.add_task(_refresh, db, user_id)
    return result.model_dump()
