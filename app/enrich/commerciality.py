"""Núcleo del Filtro Anti-Comerciales v2 (funciones puras, sin I/O).

Sustituye la `popularity` de Spotify (eliminada en 2026) por un score derivado
de los `listeners` de Last.fm, + solapamiento de tags (Jaccard).
"""
import math

DEFAULT_MAX_LISTENERS = 5_000_000


def commerciality_score(listeners: int | None, max_listeners: int = DEFAULT_MAX_LISTENERS) -> float:
    """Escala logarítmica 0-100 (los listeners tienen cola muy larga)."""
    if not listeners or listeners <= 0:
        return 0.0
    score = 100.0 * math.log10(listeners + 1) / math.log10(max_listeners + 1)
    return round(min(100.0, max(0.0, score)), 2)


def normalize_tag(tag: str) -> str:
    return tag.strip().lower()


def jaccard(a: list[str], b: list[str]) -> float:
    """Solapamiento de conjuntos de tags normalizados (0-1)."""
    sa = {normalize_tag(x) for x in a if x.strip()}
    sb = {normalize_tag(x) for x in b if x.strip()}
    if not sa or not sb:
        return 0.0
    union = len(sa | sb)
    return len(sa & sb) / union if union else 0.0


def within_underground_window(
    source: float, candidate: float, down: float = 25.0, up: float = 8.0
) -> bool:
    """Ventana ASIMÉTRICA sesgada a underground: permite bajar mucho (-down) y
    subir poco (+up) respecto al score del artista origen → capa el mainstream."""
    return (source - down) <= candidate <= (source + up)


def window_for_level(level: int, base_down: float = 25.0, base_up: float = 8.0) -> tuple[float, float]:
    """Mapea el nivel underground (0-100) a la ventana (down, up).
    Más nivel → cap más duro a lo comercial (up menor) y más margen hacia abajo (down mayor)."""
    delta = (level - 50) / 10.0
    up = max(2.0, base_up - delta)
    down = max(10.0, base_down + delta * 2)
    return round(down, 1), round(up, 1)
