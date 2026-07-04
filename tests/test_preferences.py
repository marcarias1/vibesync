"""Fase 2: aprendizaje ligero por feedback + veto + nivel underground → ventana."""
from app.agent.recommend import filter_underground
from app.enrich.commerciality import window_for_level
from app.preferences import apply_feedback, blocked_set, default_prefs


def test_dislike_aprende_sin_banear():
    p = default_prefs("u")
    d1 = apply_feedback(p, verdict="dislike", artist="X")
    assert d1["disliked_artists"]["X"] == 1.0
    d2 = apply_feedback({**p, **d1}, verdict="dislike", artist="X")
    assert d2["disliked_artists"]["X"] == 2.0        # acumula (aprende)


def test_block_veta_y_like_revierte():
    p = default_prefs("u")
    b = apply_feedback(p, verdict="block", artist="Y")
    assert "Y" in b["blocked_artists"]
    disliked = {**p, "disliked_artists": {"Z": 3.0}}
    lk = apply_feedback(disliked, verdict="like", artist="Z")
    assert "Z" in lk["loved_artists"] and "Z" not in lk["disliked_artists"]


def test_blocked_set_duro_y_ligero():
    prefs = {"blocked_artists": ["Hard"], "disliked_artists": {"Soft": 3.0, "Mild": 1.0}}
    b = blocked_set(prefs)
    assert "hard" in b and "soft" in b       # duro + ligero sobre umbral
    assert "mild" not in b                    # ligero por debajo del umbral sigue apareciendo


def test_window_for_level():
    assert window_for_level(50) == (25.0, 8.0)
    d100, u100 = window_for_level(100)
    assert u100 < 8 and d100 > 25             # más underground → cap más duro
    _, u0 = window_for_level(0)
    assert u0 > 8                             # nivel bajo → más permisivo con lo comercial


def test_filter_excluye_blocked():
    cands = [{"name": "Keep", "commerciality_score": 40, "tags": ["t"]},
             {"name": "Vetado", "commerciality_score": 40, "tags": ["t"]}]
    out = filter_underground(50, cands, source_tags=["t"], min_jaccard=0.0, blocked={"vetado"})
    assert [c["name"] for c in out] == ["Keep"]
