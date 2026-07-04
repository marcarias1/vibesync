"""Wiring de cada tool a su implementación real (db / embedder / last.fm / spotify).

El runner es agnóstico: recibe este dict de executors. En tests se sustituyen por
funciones fake, así que aquí va la versión de producción.
"""
import contextlib
from datetime import datetime, timedelta, timezone

from app.agent.recommend import filter_underground, semantic_search
from app.agent.tools import build_match
from app.enrich.commerciality import commerciality_score, window_for_level
from app.enrich.service import enrich_artist
from app.enrich.taste import score_track
from app.preferences import blocked_set, get_preferences

_ENRICH_TTL = timedelta(days=30)


def _is_stale(art: dict | None) -> bool:
    """True si el artista no está o su enriquecimiento es viejo (> TTL) → re-enriquecer."""
    if not art:
        return True
    ts = art.get("updated_at")
    if not ts:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts) > _ENRICH_TTL


def build_executors(db, embedder, user_id: str, *, lastfm=None, spotify=None, result_holder=None):
    async def user_profile(args):
        doc = await db["user_stats_cache"].find_one({"_id": user_id})
        return doc or {"note": "Sin caché de stats; importa el histórico primero."}

    async def search_tracks(args):
        match = build_match(args)
        docs = await db["tracks"].find(match).limit(args.limit).to_list(args.limit)
        return {"count": len(docs), "tracks": [
            {"uri": d.get("uri"), "name": d.get("name"), "artist": d.get("artist_name")}
            for d in docs]}

    async def semantic(args):
        try:
            docs = await semantic_search(db, embedder, args.vibe_query, args.limit)
        except Exception as exc:
            return {"error": f"vector search no disponible: {exc}"}
        return {"count": len(docs), "tracks": [
            {"uri": d.get("uri"), "name": d.get("name"), "score": d.get("score")} for d in docs]}

    async def temporal(args):
        now = datetime.now(timezone.utc)
        return {"iso": now.isoformat(), "hour": now.hour, "weekday": now.strftime("%A")}

    async def track_fame(args):
        """¿Un tema es famoso o underground? (listeners de Last.fm a nivel track)."""
        if lastfm is None:
            return {"error": "Last.fm no configurado"}
        info = await lastfm.track_info(args.artist, args.title)
        listeners = info.get("listeners") or 0
        score = commerciality_score(listeners)
        label = "muy famoso" if score >= 70 else ("conocido" if score >= 45 else "underground")
        return {"listeners": listeners, "fame_score": score, "label": label}

    async def user_prefs(args):
        p = await get_preferences(db, user_id)
        return {"underground_level": p.get("underground_level", 50),
                "loved_artists": p.get("loved_artists", []),
                "loved_tags": p.get("loved_tags", []),
                "blocked_artists": sorted(blocked_set(p))}

    async def similar_underground(args):
        """Cadena real anti-comercial: similares → enrich/score → ventana + tags."""
        if lastfm is None:
            return {"error": "Last.fm no configurado"}
        src = await enrich_artist(db, args.source_artist, lastfm=lastfm, embedder=embedder)
        src_score = src.get("commerciality_score") or 0.0
        src_tags = src.get("tags") or []

        # preferencias: veto (blocked ligero/duro) + nivel underground → ventana
        prefs = await get_preferences(db, user_id)
        blocked = blocked_set(prefs)
        down, up = window_for_level(prefs.get("underground_level", 50))

        # cap de candidatos a enriquecer → converge rápido y gasta menos Last.fm
        names = (await lastfm.similar_artists(args.source_artist, limit=args.limit * 2))[:14]
        candidates = []
        for name in names:
            a = await enrich_artist(db, name, lastfm=lastfm, embedder=embedder)
            candidates.append({
                "name": a.get("name") or name,
                "commerciality_score": a.get("commerciality_score") or 0.0,
                "tags": a.get("tags") or [],
            })
        kept = filter_underground(src_score, candidates, source_tags=src_tags,
                                  min_jaccard=0.05, down=down, up=up, blocked=blocked)
        # rankea por score de gusto (tags/comercialidad/feedback disponibles)
        for c in kept:
            c["_score"] = score_track(
                {"artist": c["name"], "tags": c["tags"], "commerciality_score": c["commerciality_score"]},
                prefs)
        kept.sort(key=lambda c: c["_score"], reverse=True)
        kept = kept[: args.limit]
        # TRACKS concretos (top tracks de cada artista), con el score del gusto
        tracks: list[dict] = []
        for c in kept:
            for tt in await lastfm.top_tracks(c["name"], limit=2):
                tracks.append({**tt, "score": c["_score"]})
        return {"source_score": src_score, "count": len(kept),
                "artists": [c["name"] for c in kept], "tracks": tracks}

    async def playlist(args):
        if spotify is None:
            return {"error": "Spotify no autenticado"}
        if args.mode == "create":
            pid = await spotify.create_new(user_id, args.playlist_name)   # siempre nueva
        else:
            pid = await spotify.get_or_create(user_id, args.playlist_name)  # reutiliza
        await spotify.set_items(pid, args.track_uris)
        return {"playlist_id": pid, "tracks": len(args.track_uris), "mode": args.mode}

    async def crear_playlist(args):
        if spotify is None:
            return {"error": "Spotify no conectado"}
        uris: list[str] = []
        misses: list[str] = []
        for t in args.tracks:
            uri = await spotify.search_track_uri(t.artist, t.title)
            if uri:
                uris.append(uri)
            else:
                misses.append(f"{t.artist} - {t.title}")
        if not uris:
            return {"error": "No encontré ninguna pista en Spotify"}
        pid = await spotify.create_new(user_id, args.playlist_name)
        await spotify.set_items(pid, uris)
        url = f"https://open.spotify.com/playlist/{pid}"
        if result_holder is not None:
            result_holder["playlist"] = {"url": url, "name": args.playlist_name, "added": len(uris)}
        return {"playlist_url": url, "added": len(uris), "not_found": misses}

    async def proponer_draft(args):
        """Propone un borrador SIN tocar Spotify; resuelve uri+carátula + score de gusto."""
        prefs = await get_preferences(db, user_id) if db is not None else {}
        tracks: list[dict] = []
        misses: list[str] = []
        for t in args.tracks:
            found = await spotify.search_track(t.artist, t.title) if spotify is not None else None
            art = await db["artists"].find_one({"name": t.artist}) if db is not None else None
            if db is not None and lastfm is not None and _is_stale(art):
                # no está o su info es vieja (TTL) → enriquece/refresca AL VUELO
                with contextlib.suppress(Exception):
                    art = await enrich_artist(db, t.artist, lastfm=lastfm, embedder=embedder) or art
            score = score_track(
                {"artist": t.artist, "tags": (art or {}).get("tags", []),
                 "commerciality_score": (art or {}).get("commerciality_score")}, prefs) if prefs else None
            tracks.append({
                # usa el nombre RESUELTO de Spotify → muestra feats y título real
                "artist": (found or {}).get("artist") or t.artist,
                "title": (found or {}).get("name") or t.title,
                "uri": (found or {}).get("uri"),
                "cover_url": (found or {}).get("cover_url"),
                "score": score,
            })
            if spotify is not None and not found:
                misses.append(f"{t.artist} - {t.title}")
        if result_holder is not None:
            result_holder["draft"] = {"name": args.playlist_name, "tracks": tracks, "not_found": misses}
        return {"proposed": len(tracks), "not_found": misses}

    async def _resolve_toptrack(artist: str, exclude: set):
        """Un top track del artista resoluble en Spotify y que no esté ya (excludes uris)."""
        if lastfm is None:
            return None
        with contextlib.suppress(Exception):
            for tt in await lastfm.top_tracks(artist, limit=4):
                found = await spotify.search_track(tt["artist"], tt["name"]) if spotify is not None else None
                uri = (found or {}).get("uri")
                if uri and uri not in exclude:
                    return {"artist": (found or {}).get("artist") or tt["artist"],
                            "title": (found or {}).get("name") or tt["name"],
                            "uri": uri, "cover_url": (found or {}).get("cover_url")}
        return None

    async def asegurar_playlist(args):
        """Revisa el borrador propuesto y SUGIERE mejoras (no las aplica)."""
        draft = (result_holder or {}).get("draft") or {}
        tracks = draft.get("tracks", [])
        not_found = draft.get("not_found", [])
        have_artists = {(t.get("artist") or "").lower() for t in tracks}
        exclude = {t.get("uri") for t in tracks if t.get("uri")}
        suggestions: list[dict] = []

        # 1) rellenar los temas que no se resolvieron en Spotify
        for nf in not_found[:5]:
            artist = nf.split(" - ")[0].strip()
            alt = await _resolve_toptrack(artist, exclude)
            if alt:
                exclude.add(alt["uri"])
                suggestions.append({"type": "fill",
                                    "from": {"artist": artist, "title": nf.split(" - ", 1)[-1]},
                                    "to": alt,
                                    "reason": f"'{nf}' no se resolvió en Spotify; alternativa de {artist}."})

        # 2) artistas que el usuario nombró y NO están en la playlist
        for ra in (getattr(args, "requested_artists", None) or [])[:6]:
            ra = (ra or "").strip()
            if ra and ra.lower() not in have_artists:
                alt = await _resolve_toptrack(ra, exclude)
                if alt:
                    exclude.add(alt["uri"])
                    suggestions.append({"type": "add", "to": alt,
                                        "reason": f"Pediste {ra} y no estaba en la playlist."})

        # 3) reemplazar el tema más flojo (si su score es muy bajo)
        scored = [t for t in tracks if t.get("score") is not None and t.get("uri")]
        if scored:
            worst = min(scored, key=lambda t: t["score"])
            if worst["score"] < 40 and lastfm is not None:
                with contextlib.suppress(Exception):
                    for s in await lastfm.similar_artists(worst.get("artist", ""), limit=5):
                        alt = await _resolve_toptrack(s, exclude)
                        if alt:
                            suggestions.append({"type": "replace",
                                                "from": {"artist": worst.get("artist"), "title": worst.get("title"), "uri": worst.get("uri")},
                                                "to": alt,
                                                "reason": f"'{worst.get('title')}' tenía score bajo ({worst['score']}); alternativa más afín."})
                            break
        if result_holder is not None:
            result_holder["suggestions"] = suggestions
        return {"suggestions": len(suggestions), "detail": suggestions}

    return {
        "get_user_music_profile": user_profile,
        "search_tracks_database": search_tracks,
        "semantic_track_search": semantic,
        "get_temporal_context": temporal,
        "get_track_fame": track_fame,
        "get_user_preferences": user_prefs,
        "find_similar_underground_tracks": similar_underground,
        "spotify_playlist_controller": playlist,
        "crear_playlist_spotify": crear_playlist,
        "proponer_playlist_draft": proponer_draft,
        "asegurar_playlist": asegurar_playlist,
    }
