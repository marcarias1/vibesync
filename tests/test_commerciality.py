from app.enrich.commerciality import (
    commerciality_score,
    jaccard,
    within_underground_window,
)


def test_score_bounds_and_monotonic():
    assert commerciality_score(0) == 0.0
    assert commerciality_score(None) == 0.0
    assert commerciality_score(100) < commerciality_score(1_000_000)
    assert commerciality_score(50_000_000) == 100.0  # capado


def test_jaccard():
    assert jaccard(["Rock", "Pop"], ["rock"]) == 0.5  # normaliza mayúsculas
    assert jaccard([], ["x"]) == 0.0
    assert jaccard(["trap"], ["trap"]) == 1.0


def test_window_asimetrica():
    assert within_underground_window(50, 30)       # bajar 20 -> ok
    assert within_underground_window(50, 55)       # subir 5 -> ok
    assert not within_underground_window(50, 70)   # demasiado comercial (+20)
    assert not within_underground_window(50, 20)   # demasiado abajo (-30)
