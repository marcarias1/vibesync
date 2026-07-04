"""DEMO END-TO-END REAL (sin login de Spotify): DeepSeek + Last.fm + BGE-M3 + $vectorSearch.

Siembra un histórico de ejemplo, enriquece con Last.fm REAL, calcula comercialidad
real, embebe con BGE-M3 real, indexa en Atlas-local y deja que el agente DeepSeek
REAL use las herramientas para construir una playlist underground.
La escritura en Spotify se simula (dry-run) porque requiere login interactivo.

Uso:  .venv/bin/python scripts/demo_live.py
"""
import asyncio
from datetime import datetime, timedelta, timezone

from pymongo import AsyncMongoClient
from pymongo.operations import SearchIndexModel

from app.agent.executors import build_executors
from app.agent.llm import DeepSeekClient
from app.agent.runner import run_agent
from app.agent.tools import ARG_MODELS, TOOL_SCHEMAS
from app.config import get_settings
from app.enrich.embeddings import get_embedder
from app.enrich.lastfm import LastFmClient
from app.enrich.service import enrich_artist
from app.ingest.stats import rebuild_user_stats
from app.enrich.tracks import rebuild_tracks
from app.ingest.importer import ingest

USER = "demo_live"
SEED = [  # (artista, track, uri, nº plays)
    ("Bad Bunny", "Tití Me Preguntó", "spotify:track:d1", 8),
    ("Feid", "Classy 101", "spotify:track:d2", 6),
    ("Mora", "Volando", "spotify:track:d3", 5),
    ("Saramalacara", "Nostalgia", "spotify:track:d4", 4),
    ("Bb trickz", "Missn tickz", "spotify:track:d5", 7),
    ("Ralphie Choo", "Muascador", "spotify:track:d6", 3),
]


class DryRunSpotify:
    async def get_or_create(self, u, n): return "pl_dryrun"
    async def create_new(self, u, n): return "pl_dryrun"
    async def set_items(self, pid, uris): self.last = (pid, uris)
    async def aclose(self): pass


async def _seed(db, embedder, lastfm):
    await db["playback_history"].delete_many({"user_id": USER})
    await db["artists"].delete_many({})
    await db["tracks"].delete_many({})
    base = datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    raw, t = [], 0
    for artist, track, uri, plays in SEED:
        for _ in range(plays):
            raw.append({"ts": (base + timedelta(hours=t)).isoformat(), "ms_played": 90000,
                        "spotify_track_uri": uri, "reason_end": "trackdone",
                        "master_metadata_track_name": track,
                        "master_metadata_album_artist_name": artist})
            t += 1
    await ingest(db, USER, raw)
    for artist, *_ in SEED:
        await enrich_artist(db, artist, lastfm=lastfm, embedder=embedder)  # Last.fm REAL
    await rebuild_tracks(db, USER, embedder=embedder)                      # BGE-M3 REAL
    await rebuild_user_stats(db, USER)


async def _ensure_vector_index(coll):
    names = {ix["name"] async for ix in await coll.list_search_indexes()}
    if "vec_tracks" not in names:
        await coll.create_search_index(SearchIndexModel(
            name="vec_tracks", type="vectorSearch",
            definition={"fields": [{"type": "vector", "path": "embedding",
                                    "numDimensions": 1024, "similarity": "cosine"}]}))
    for _ in range(180):
        ix = [i async for i in await coll.list_search_indexes() if i["name"] == "vec_tracks"]
        if ix and ix[0].get("queryable"):
            return
        await asyncio.sleep(1)


def _wrap(executors):
    wrapped = {}
    for name, fn in executors.items():
        async def w(args, _fn=fn, _n=name):
            shown = args.model_dump() if hasattr(args, "model_dump") else args
            print(f"   🔧 {_n}  {shown}", flush=True)
            r = await _fn(args)
            print(f"      → {str(r)[:180]}", flush=True)
            return r
        wrapped[name] = w
    return wrapped


async def main():
    s = get_settings()
    client = AsyncMongoClient(s.mongo_uri, tz_aware=True)
    db = client[s.mongo_db]
    embedder = get_embedder()  # BGE-M3 real (use_real_embeddings=true)
    lastfm = LastFmClient(s.lastfm_api_key)

    print("· Sembrando histórico + enriquecimiento REAL (Last.fm + BGE-M3)…", flush=True)
    await _seed(db, embedder, lastfm)
    print("· Índice vectorial → READY…", flush=True)
    await _ensure_vector_index(db["tracks"])

    print("\n· Comercialidad REAL (Last.fm listeners → 0-100):")
    async for a in db["artists"].find({}, {"name": 1, "commerciality_score": 1, "tags": 1}).sort("commerciality_score", -1):
        print(f"   {a.get('commerciality_score'):>6}  {a['name']:<16} {a.get('tags', [])[:3]}")

    executors = _wrap(build_executors(db, embedder, USER, lastfm=lastfm, spotify=DryRunSpotify()))
    llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
    prompt = ("Escucho reggaeton y trap latino. Crea una playlist llamada 'Noche Underground' "
              "para programar de noche: temas parecidos a lo mío pero MÁS UNDERGROUND, evitando "
              "lo más comercial. Usa las herramientas, crea la playlist y explícame la selección.")
    demo_system = (
        "Eres el DJ de VibeSync. Construye una playlist de tracks concretos.\n"
        "- `find_similar_underground_tracks` YA devuelve TRACKS underground (campo 'tracks': "
        "artista+título) filtrados de lo comercial: son tus candidatos principales. Llámala 1-2 "
        "veces sobre los artistas que escucha el usuario.\n"
        "- `get_user_music_profile`: el contexto del usuario (llámala una sola vez).\n"
        "- `search_tracks_database` SOLO contiene el historial del propio usuario; NO busques ahí "
        "artistas nuevos uno a uno.\n"
        "- Todavía no hay login de Spotify: NO llames a `spotify_playlist_controller`. En cuanto "
        "tengas ~12 tracks, DEJA de usar herramientas y responde con la lista final numerada "
        "(artista - título) y una breve explicación de por qué encajan y por qué son underground."
    )
    print(f"\n🗣️  Usuario: {prompt}\n\n🤖 Agente DeepSeek ({s.deepseek_model}) trabajando:\n", flush=True)
    answer = await run_agent(llm, executors, ARG_MODELS, prompt,
                             tool_schemas=TOOL_SCHEMAS, max_iters=10, system=demo_system)
    print(f"\n💬 Respuesta del agente:\n{answer}")

    await llm.aclose()
    await lastfm.aclose()
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
