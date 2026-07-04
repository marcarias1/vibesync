"""Importador idempotente del histórico GDPR de Spotify.

Flujo: parse → filtro de calidad → docs con _id determinista →
insert_many(ordered=False) tragando duplicados (E11000).
"""
import logging

from pymongo.errors import BulkWriteError

from app.config import get_settings
from app.db.models import PlaybackEvent
from app.ingest.schemas import ImportResult, RawStreamEntry

log = logging.getLogger(__name__)

# reason_end que indican que NO fue una escucha "real" aunque supere los 30s.
SKIP_REASONS = {"fwdbtn"}


def parse_entries(raw: list[dict]) -> list[RawStreamEntry]:
    out: list[RawStreamEntry] = []
    for r in raw:
        try:
            out.append(RawStreamEntry.model_validate(r))
        except Exception as exc:  # registro corrupto → se ignora, no aborta
            log.debug("Registro ignorado: %s", exc)
    return out


def filter_entries(entries: list[RawStreamEntry]) -> list[RawStreamEntry]:
    """Filtro estricto: >=30s, con URI de track, y que no sea un skip."""
    min_ms = get_settings().min_ms_played
    return [
        e
        for e in entries
        if e.ms_played >= min_ms
        and e.spotify_track_uri
        and e.reason_end not in SKIP_REASONS
    ]


def to_playback_docs(user_id: str, entries: list[RawStreamEntry]) -> list[dict]:
    docs: list[dict] = []
    for e in entries:
        uri = e.spotify_track_uri
        if uri is None:  # el filtro ya lo garantiza; narrowing para el tipado
            continue
        pe = PlaybackEvent(
            _id=PlaybackEvent.make_id(user_id, uri, e.ts),
            user_id=user_id,
            track_uri=uri,
            ts=e.ts,
            ms_played=e.ms_played,
            reason_start=e.reason_start,
            reason_end=e.reason_end,
            shuffle=e.shuffle,
            skipped=e.skipped,
            platform=e.platform,
            track_name=e.master_metadata_track_name,
            artist_name=e.master_metadata_album_artist_name,
        )
        docs.append(pe.model_dump(by_alias=True))
    return docs


async def ingest(db, user_id: str, raw: list[dict]) -> ImportResult:
    entries = parse_entries(raw)
    kept = filter_entries(entries)
    docs = to_playback_docs(user_id, kept)

    inserted = 0
    duplicates = 0
    if docs:
        try:
            res = await db["playback_history"].insert_many(docs, ordered=False)
            inserted = len(res.inserted_ids)
        except BulkWriteError as bwe:
            write_errors = bwe.details.get("writeErrors", [])
            non_dup = [e for e in write_errors if e.get("code") != 11000]
            if non_dup:
                raise  # error real, no un simple duplicado
            duplicates = len(write_errors)
            inserted = bwe.details.get("nInserted", len(docs) - duplicates)

    return ImportResult(
        total=len(entries), kept=len(kept), inserted=inserted, duplicates=duplicates
    )
