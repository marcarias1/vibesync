"""track2vec: tracks del mismo cluster de escucha quedan cerca; corte por huecos.

Nota: word2vec agrupa por CONTEXTO compartido (sustituibilidad), no por mera
co-ocurrencia en pares. Por eso usamos clusters de 3 tracks con contextos
solapados, que es como se comporta un histórico real por géneros/moods.
"""
from datetime import datetime, timezone

from app.enrich.track2vec import build_sessions, train_track2vec


def test_same_cluster_tracks_are_more_similar_on_average():
    # 2 clusters de 4 tracks (reggaeton R*, rock K*) en sesiones de orden variado.
    # word2vec es estocástico en datos pequeños: comparamos la similitud MEDIA
    # intra-cluster vs inter-cluster (señal robusta), no un top-k concreto.
    reg = [["R1", "R2", "R3", "R4"], ["R2", "R4", "R1", "R3"],
           ["R3", "R1", "R4", "R2"], ["R4", "R3", "R2", "R1"]]
    rock = [["K1", "K2", "K3", "K4"], ["K2", "K4", "K1", "K3"],
            ["K3", "K1", "K4", "K2"], ["K4", "K3", "K2", "K1"]]
    sessions = [s for s in reg for _ in range(15)] + [s for s in rock for _ in range(15)]

    model = train_track2vec(sessions, dim=32, window=5, min_count=1, epochs=150)
    intra = sum(model.wv.similarity("R1", r) for r in ["R2", "R3", "R4"]) / 3
    cross = sum(model.wv.similarity("R1", k) for k in ["K1", "K2", "K3", "K4"]) / 4
    assert intra > cross  # los del mismo cluster de escucha están más cerca


async def test_build_sessions_splits_on_gap(db):
    base = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    raw = [
        {"ts": base.isoformat(), "ms_played": 60000,
         "spotify_track_uri": "A", "reason_end": "trackdone"},
        {"ts": base.replace(minute=3).isoformat(), "ms_played": 60000,
         "spotify_track_uri": "B", "reason_end": "trackdone"},
        # hueco de ~2h → nueva sesión
        {"ts": base.replace(hour=12).isoformat(), "ms_played": 60000,
         "spotify_track_uri": "C", "reason_end": "trackdone"},
    ]
    await ingest_helper(db, raw)
    assert await build_sessions(db, "u1", gap_minutes=30) == [["A", "B"], ["C"]]


async def ingest_helper(db, raw):
    from app.ingest.importer import ingest
    await ingest(db, "u1", raw)
