"""Motor de GUSTO: puntúa cada track (0-100) combinando ritmo (audio), lyrics,
contenido (embedding), tags, alineación underground y feedback del usuario.

Cada señal que falta se ignora y se re-normaliza el peso → funciona con datos
parciales y va afinando según se enriquecen los tracks y llega feedback.
"""
import math

from app.preferences import get_preferences, save_preferences

_AUDIO_KEYS = ("energy", "danceability", "valence")  # normalizadas 0-1


def _cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return s / (na * nb) if na and nb else 0.0


def _audio_match(track_audio: dict | None, profile: dict | None) -> float | None:
    if not track_audio or not profile:
        return None
    diffs = [abs(track_audio[k] - profile[k]) for k in _AUDIO_KEYS
             if k in track_audio and k in profile]
    return 1 - sum(diffs) / len(diffs) if diffs else None


def score_track(track: dict, prefs: dict) -> float:
    """Puntúa un track (0-100). `track` puede traer embedding/lyrics_embedding/
    audio/tags/commerciality_score/artist(_name); usa lo que haya."""
    artist = (track.get("artist_name") or track.get("artist") or "")
    if artist.lower() in {a.lower() for a in prefs.get("blocked_artists", [])}:
        return 0.0

    w = prefs.get("weights") or {}
    parts: list[tuple[float, float]] = []  # (peso, valor 0-1)

    cc = prefs.get("content_centroid")
    if cc and track.get("embedding"):
        parts.append((w.get("content", 0.35), (_cosine(track["embedding"], cc) + 1) / 2))

    lc = prefs.get("lyrics_centroid")
    if lc and track.get("lyrics_embedding"):
        parts.append((w.get("lyrics", 0.15), (_cosine(track["lyrics_embedding"], lc) + 1) / 2))

    am = _audio_match(track.get("audio"), prefs.get("audio_profile"))
    if am is not None:
        parts.append((w.get("audio", 0.20), max(0.0, am)))

    tags = {t.lower() for t in track.get("tags", [])}
    if tags:
        loved = {t.lower() for t in prefs.get("loved_tags", [])}
        dtags = {t.lower() for t in prefs.get("disliked_tags", {})}
        val = 0.5 + 0.5 * (len(tags & loved) - len(tags & dtags)) / len(tags)
        parts.append((w.get("tags", 0.20), max(0.0, min(1.0, val))))

    cs = track.get("commerciality_score")
    if cs is not None:
        target = 100 - prefs.get("underground_level", 50)  # más underground → menor comercialidad ideal
        parts.append((w.get("underground", 0.10), max(0.0, 1 - abs(cs - target) / 100)))

    if parts:
        tw = sum(p for p, _ in parts)
        base = 100 * sum(p * v for p, v in parts) / tw if tw else 50.0
    else:
        base = 50.0

    # penalización por dislike ligero (cada dislike ~ -15%, suelo 30%)
    dw = prefs.get("disliked_artists", {}).get(artist, 0.0)
    base *= max(0.3, 1 - 0.15 * dw)
    return round(max(0.0, min(100.0, base)), 1)


def _mean(vectors: list[list[float] | None]) -> list[float] | None:
    vs = [v for v in vectors if v]
    if not vs:
        return None
    dim = len(vs[0])
    return [sum(v[i] for v in vs) / len(vs) for i in range(dim)]


def _mean_audio(audios: list[dict | None]) -> dict | None:
    xs = [a for a in audios if a]
    if not xs:
        return None
    keys = set().union(*[a.keys() for a in xs])
    return {k: sum(a.get(k, 0) for a in xs) / len(xs) for k in keys}


async def rebuild_taste(db, user_id: str) -> dict:
    """Recalcula centroides (contenido/lyrics) y perfil de audio desde los tracks
    amados (o los más escuchados si aún no hay 'loved')."""
    prefs = await get_preferences(db, user_id)
    loved = {a.lower() for a in prefs.get("loved_artists", [])}
    docs = await db["tracks"].find({}).sort("play_count", -1).limit(300).to_list(300)
    with_emb = [d for d in docs if d.get("embedding")]
    liked = [d for d in with_emb if (d.get("artist_name") or "").lower() in loved] or with_emb[:60]
    patch = {
        "content_centroid": _mean([d.get("embedding") for d in liked]),
        "lyrics_centroid": _mean([d.get("lyrics_embedding") for d in liked]),
        "audio_profile": _mean_audio([d.get("audio") for d in liked]),
    }
    await save_preferences(db, user_id, patch)
    return patch
