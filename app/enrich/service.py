"""Servicio de enriquecimiento de artistas (orquesta I/O + funciones puras).

Combina Last.fm (listeners/tags), MusicBrainz opcional (mbid/géneros) y el
embedder para construir el perfil textual, y persiste el resultado en `artists`.
"""
from datetime import datetime, timezone

from app.enrich.commerciality import commerciality_score, normalize_tag
from app.enrich.embeddings import artist_profile_text


async def enrich_artist(db, name: str, *, lastfm, embedder, musicbrainz=None) -> dict:
    """Enriquece un artista y hace upsert idempotente en la colección `artists`."""
    # 1) Info de Last.fm (listeners, playcount, tags, mbid).
    info = await lastfm.artist_info(name)
    display_name = info.get("name") or name
    listeners = info.get("listeners") or 0
    playcount = info.get("playcount") or 0
    mbid = info.get("mbid") or None
    # Tags de calidad (getTopTags con recuento → menos ruido); fallback a getinfo.
    if hasattr(lastfm, "clean_tags"):
        raw_tags = await lastfm.clean_tags(name)
    else:
        raw_tags = info.get("tags", [])
    tags = _dedup([normalize_tag(t) for t in raw_tags if t and t.strip()])

    # 2) Score de comercialidad (log de listeners, 0-100).
    score = commerciality_score(listeners)

    # 3) Géneros vía MusicBrainz (opcional); completa mbid si Last.fm no lo trae.
    genres: list[str] = []
    if musicbrainz is not None:
        mb = await musicbrainz.search_artist(display_name)
        if mb:
            genres = _dedup([normalize_tag(g) for g in mb.get("genres", []) if g and g.strip()])
            mbid = mbid or mb.get("mbid") or None

    # 4) Perfil textual (con bio descriptiva) + embedding.
    profile = artist_profile_text(display_name, tags, genres, bio=info.get("bio"))
    embedding = embedder.encode(profile)

    # 5) _id determinista: mbid si existe, si no el nombre normalizado en minúsculas.
    doc_id = mbid or display_name.strip().lower()

    # 6) Upsert idempotente con updated_at.
    update = {
        "$set": {
            "name": display_name,
            "mbid": mbid,
            "tags": tags,
            "genres": genres,
            "bio": info.get("bio") or "",
            "lastfm_listeners": listeners,
            "lastfm_playcount": playcount,
            "commerciality_score": score,
            "embedding": embedding,
            "updated_at": datetime.now(timezone.utc),
        }
    }
    await db["artists"].update_one({"_id": doc_id}, update, upsert=True)

    # 7) Devuelve el doc persistido.
    return await db["artists"].find_one({"_id": doc_id})


async def enrich_artists(db, names, *, lastfm, embedder, musicbrainz=None) -> list[dict]:
    """Enriquece una lista de artistas (secuencial: respeta rate limits externos)."""
    docs: list[dict] = []
    for name in names:
        docs.append(
            await enrich_artist(db, name, lastfm=lastfm, embedder=embedder, musicbrainz=musicbrainz)
        )
    return docs


def _dedup(items: list[str]) -> list[str]:
    """Elimina duplicados preservando el orden de aparición."""
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
