import math

from app.enrich.embeddings import FakeEmbedder, artist_profile_text


def test_fake_deterministic_and_normalized():
    e = FakeEmbedder(1024)
    a = e.encode("bad bunny — trap latino")
    b = e.encode("bad bunny — trap latino")
    assert a == b                       # determinista
    assert len(a) == 1024               # dimensión correcta
    assert e.encode("x") != e.encode("y")
    assert abs(math.sqrt(sum(v * v for v in a)) - 1.0) < 1e-6  # normalizado


def test_profile_text():
    assert artist_profile_text("Rosalía", ["flamenco"], ["pop"]) == "Rosalía — flamenco — pop"
    assert artist_profile_text("X", [], []) == "X"
