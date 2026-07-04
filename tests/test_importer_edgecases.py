"""Casos límite del importador: entradas malformadas, listas vacías, ingesta vacía."""
from app.ingest.importer import filter_entries, ingest, parse_entries

USER = "importer_edge_test"


def _valida(track_uri, ts):
    """Registro crudo válido estilo GDPR de Spotify."""
    return {
        "ts": ts,
        "ms_played": 120_000,
        "spotify_track_uri": track_uri,
        "master_metadata_track_name": "Nombre",
        "master_metadata_album_artist_name": "Artista",
        "reason_start": "trackdone",
        "reason_end": "trackdone",
    }


def test_parse_entries_ignora_malformadas():
    raw = [
        _valida("spotify:track:A", "2026-01-05T14:00:00Z"),
        {"basura": "sin campos requeridos"},          # sin ts ni ms_played
        {"ts": "no-es-fecha", "ms_played": 1000},     # ts inválido
        "esto no es ni un dict",                       # tipo erróneo
        _valida("spotify:track:B", "2026-01-05T15:00:00Z"),
    ]
    entries = parse_entries(raw)
    # Solo las 2 válidas sobreviven; las malformadas se ignoran sin abortar.
    assert len(entries) == 2


def test_filter_entries_lista_vacia():
    assert filter_entries([]) == []


async def test_ingest_vacio(db):
    res = await ingest(db, USER, [])
    assert res.inserted == 0
    assert res.total == 0
    assert res.kept == 0
    assert res.duplicates == 0
