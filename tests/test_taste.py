"""Fase 3: score_track combina ritmo/lyrics/contenido/tags/underground/feedback."""
from app.enrich.taste import score_track


def test_blocked_da_cero():
    assert score_track({"artist": "X"}, {"blocked_artists": ["x"]}) == 0.0


def test_contenido_similar_puntua_mas():
    prefs = {"content_centroid": [1.0, 0.0, 0.0], "weights": {"content": 1.0}}
    alto = score_track({"artist": "a", "embedding": [1.0, 0.0, 0.0]}, prefs)
    bajo = score_track({"artist": "b", "embedding": [-1.0, 0.0, 0.0]}, prefs)
    assert alto > bajo


def test_audio_ritmo_cercano_puntua_mas():
    prefs = {"audio_profile": {"energy": 0.8, "danceability": 0.8, "valence": 0.7},
             "weights": {"audio": 1.0}}
    cerca = score_track({"artist": "a", "audio": {"energy": 0.8, "danceability": 0.8, "valence": 0.7}}, prefs)
    lejos = score_track({"artist": "b", "audio": {"energy": 0.1, "danceability": 0.1, "valence": 0.1}}, prefs)
    assert cerca > lejos


def test_alineacion_underground():
    prefs = {"underground_level": 90, "weights": {"underground": 1.0}}  # target comercialidad ~10
    under = score_track({"artist": "a", "commerciality_score": 10}, prefs)
    comm = score_track({"artist": "b", "commerciality_score": 90}, prefs)
    assert under > comm


def test_dislike_penaliza():
    prefs = {"disliked_artists": {"X": 2.0}, "underground_level": 50, "weights": {"underground": 1.0}}
    malo = score_track({"artist": "X", "commerciality_score": 50}, prefs)
    bueno = score_track({"artist": "Y", "commerciality_score": 50}, prefs)
    assert malo < bueno
