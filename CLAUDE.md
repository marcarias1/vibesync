# CLAUDE.md — VibeSync

Guía para agentes de Claude Code trabajando en este repo. Léela entera antes de tocar código.

## Qué es VibeSync

Backend **FastAPI async (Python 3.12)** de un **agente DJ predictivo** para Spotify: importa tu
histórico de escucha, enriquece la música con señales externas y deja que un LLM (con tool-calling)
construya playlists coherentes evitando el mainstream comercial, escribiéndolas de vuelta en Spotify.

## Decisión arquitectónica clave (2026): Spotify solo es OAuth + histórico + escritura

En **febrero de 2026 Spotify recortó su API**. Ya NO se puede usar para la *inteligencia*:

- Se **eliminó `popularity`** de track.
- `genres` y `popularity` de **artista quedaron deprecados**.
- **Audio Features, Related Artists y Recommendations murieron** (endpoints muertos).
- **Search capado a 10 resultados**.
- **Premium obligatorio** incluso en development mode.

Por eso Spotify se limita a **tres cosas**: (1) OAuth (login), (2) ingesta del **histórico GDPR**
(`Streaming_History_Audio_*.json` que el usuario descarga de su cuenta), y (3) **escritura de
playlists**. Toda la inteligencia se reconstruye fuera de Spotify:

- **Last.fm** (gratis): `listeners` como **proxy de comercialidad**, `tags`, artistas `similares`.
- **MusicBrainz** (gratis, 1 req/s, User-Agent obligatorio): mbid + géneros.
- **Embeddings locales BGE-M3** sobre el perfil textual del artista.
- **MongoDB Vector Search local** (`$vectorSearch`) para búsqueda semántica por "vibe".

Stack ~100% gratis; único coste real: DeepSeek (céntimos).

## Stack

- **FastAPI** + `uvicorn[standard]`.
- **PyMongo `AsyncMongoClient`** — driver async oficial. **NO uses Motor (deprecado).**
- **Pydantic v2** + `pydantic-settings` (config vía `.env`).
- **DeepSeek V4 Flash** vía endpoint **OpenAI-compatible** (`/chat/completions`).
- **Embeddings BGE-M3** (`sentence-transformers`, extra `ml`) con **`FakeEmbedder`** determinista
  para dev/tests sin torch (`use_real_embeddings=False` por defecto).
- **Fernet** (`cryptography`) para cifrar refresh tokens en reposo.
- **MongoDB** vía imagen `mongodb/mongodb-atlas-local` (single-node RS + `mongot` para vector search).

## Mapa de módulos (`app/`)

- `main.py` — entrypoint FastAPI; `lifespan` crea índices y arranca el **scheduler** APScheduler; monta routers `import`, `agent` y `auth`; `/health`.
- `config.py` — `Settings` (pydantic-settings) + `get_settings()` cacheado con `lru_cache`.
- `db/client.py` — singleton `AsyncMongoClient` (uno por proceso/event loop, NO thread-safe).
- `db/indexes.py` — `ensure_indexes()` idempotente: índices regulares + índice vectorial `vec_tracks`.
- `db/models.py` — modelos Pydantic v2 = esquema de colecciones (User, Artist, Track, PlaybackEvent, UserTrackVibe).
- `ingest/schemas.py` — `RawStreamEntry` (formato GDPR de Spotify) + `ImportResult`.
- `ingest/importer.py` — parse → filtro de calidad → `_id` determinista → `insert_many(ordered=False)`.
- `ingest/aggregations.py` — recalcula `user_tracks_vibe` con `$group + $merge` (idempotente).
- `ingest/stats.py` — precálculo compacto en `user_stats_cache` (un `$facet`) para inyectar al LLM sin gastar tokens.
- `ingest/router.py` — `POST /import/streaming-history` (multipart) + cadena en background: `recompute_user_vibe` → `rebuild_user_stats` → `rebuild_tracks`.
- `enrich/lastfm.py` — cliente Last.fm (artist_info, similar_artists, top_tags).
- `enrich/musicbrainz.py` — cliente MusicBrainz (search_artist → mbid/géneros).
- `enrich/commerciality.py` — funciones puras: `commerciality_score` (log10 de listeners), `jaccard`, ventana underground asimétrica.
- `enrich/embeddings.py` — `Embedder` (Protocol), `FakeEmbedder`, `BGEEmbedder` (lazy import), `get_embedder()`.
- `enrich/service.py` — orquesta enriquecimiento de artistas y hace upsert idempotente en `artists`.
- `enrich/tracks.py` — `rebuild_tracks`: siembra la colección `tracks` (un doc por track del histórico) con `embedding` del perfil textual, `play_count`, y **denormaliza** `commerciality_score`/`tags` del artista para que la búsqueda semántica y el filtro underground operen a nivel track.
- `agent/llm.py` — capa LLM abstraída (`LLMClient` Protocol), `DeepSeekClient`, `FakeLLM` para tests.
- `agent/tools.py` — modelos Pydantic de argumentos + `build_match` blindado + `TOOL_SCHEMAS` (function-calling) + `ARG_MODELS`.
- `agent/executors.py` — wiring de cada tool a su implementación real (db/embedder/lastfm/spotify **ya cableados**). `find_similar_underground_tracks` ejecuta la cadena anti-comercial real (similares → enrich/score → `filter_underground` por ventana + tags); `search_tracks_database` honra `min_plays` (denormalizado en `tracks`).
- `agent/recommend.py` — `vector_search_pipeline`/`semantic_search` + **Filtro Anti-Comerciales v2** (`filter_underground`).
- `agent/runner.py` — bucle de tool-calling con validación y auto-reparación de argumentos.
- `agent/router.py` — `POST /agent/chat`; construye DeepSeek + `build_executors` con Last.fm y Spotify según claves/`access_token`.
- `scheduler.py` — **AsyncIOScheduler** (APScheduler) arrancado en el lifespan; job `refresh_stats` cada **6h** que recalcula el `user_stats_cache` de todos los usuarios. Sustituye a los Triggers de Atlas (no hay en Mongo local).
- `spotify/auth.py` — OAuth 2.0 **PKCE** (sin client secret): `generate_pkce`, `authorize_url`, `exchange_code`, `refresh_token`.
- `spotify/router.py` — router **`/auth`** montado: `/auth/login` (genera PKCE + `state`) y `/auth/callback` (intercambia code, lee `/me`, guarda el **refresh token cifrado con Fernet** en `users`).
- `spotify/playlists.py` — `SpotifyPlaylistController`: get-or-create idempotente + troceo a 100 URIs/request.
- `security/crypto.py` — `encrypt`/`decrypt` de refresh tokens con Fernet.

## Convenciones (respétalas)

- **Comentarios y mensajes en español.** Todo el código ya está documentado así.
- **Async PyMongo**: `AsyncMongoClient`, y `cursor = await coll.aggregate(...)` seguido de
  `await cursor.to_list(None)`. En agregaciones con `$merge` **hay que agotar el cursor** o el
  `$merge` no se ejecuta.
- **Idempotencia del importador**: `_id` determinista `PlaybackEvent.make_id()`
  (`user_id:track_uri:ts.isoformat()`) + `insert_many(ordered=False)` que se traga los duplicados
  E11000; el resto de errores sí se propagan.
- **Contadores por RECÁLCULO, nunca `$inc`**: `user_tracks_vibe` y `user_stats_cache` se regeneran
  desde `playback_history` (fuente de verdad) con `$group + $merge` / `$facet + upsert`. Usar `$inc`
  doblaría los counts al resubir el mismo fichero.
- **`playback_history` es colección REGULAR (no time-series).** Motivo: la idempotencia exige un
  índice UNIQUE sobre el `_id` determinista, y las colecciones time-series de MongoDB **no admiten
  índices unique**. Con índices compuestos se obtiene casi todo el rendimiento temporal sin perderla.
- **Seguridad de tools**: el LLM rellena los args → los modelos Pydantic de `agent/tools.py` blindan
  contra NoSQL injection (texto whitelisted, rechazo de `$...`, regex escapado con `re.escape`,
  URIs `spotify:track:` validadas). No relajes estas validaciones.
- **Upserts idempotentes** con `updated_at` en enrich/stats/playlists.

## Cómo arrancar / testear (ver `Makefile`)

```bash
make install    # uv pip install -e ".[dev]"  (añade el extra ml para BGE-M3 real)
make mongo-up   # docker compose up -d  (Atlas local: RS single-node + mongot)
make test       # PYTHONPATH=. .venv/bin/python -m pytest tests -q
make run        # uvicorn app.main:app --reload   → curl http://127.0.0.1:8000/health
make lint       # ruff check app tests
```

El contenedor Docker expone Mongo en el puerto **27020** del host (27017 estaba ocupado por el Mongo
del sistema) → `mongodb://127.0.0.1:27020`. Los tests que necesitan Mongo se **saltan** solos si no
hay servidor escuchando (ver `tests/conftest.py`) y usan la base **`vibesync_test`**; apunta
`MONGO_URI`/`MONGO_TEST_URI` a `mongodb://127.0.0.1:27020` para correrlos contra el Docker.

## Estado actual

**Hecho y con tests** (`tests/`, ~18 ficheros, ~40+ tests en verde): importador (unit + integración),
agregaciones de counts, precálculo de stats, seeding de `tracks`, comercialidad/Jaccard/ventana
underground, embeddings (FakeEmbedder), servicio de enriquecimiento, cliente Last.fm, búsqueda
semántica + filtro underground, seguridad de tools, crypto Fernet, **OAuth PKCE de Spotify (`/auth`
montado, refresh token cifrado en `users`)**, controlador de playlists, **executors de integración
(lastfm/spotify cableados)**, **scheduler** (`refresh_stats`), y el runner del agente con `FakeLLM`.

- **`$vectorSearch` REAL verificado** contra `mongodb-atlas-local` + embeddings **BGE-M3 reales**
  (ver `scripts/verify_semantic.py`).
- La cadena anti-comercial se aplica de verdad en `find_similar_underground_tracks`
  (enrich → score → `filter_underground`); `search_tracks_database` honra `min_plays`. `skip_ratio`
  fue eliminado (métrica muerta).

**Falta / pendiente** — todo lo que exige **claves o login reales** (lo demostrable sin claves ya está
hecho y probado):

- **Login OAuth real de Spotify**: requiere `SPOTIFY_CLIENT_ID` + app registrada; el flujo `/auth`
  está montado pero no se ha ejercitado contra Spotify real (queda validar el refresco de access
  token en escritura de playlists).
- **Agente contra DeepSeek real**: probado con `FakeLLM`; falta validar el tool-loop contra la API
  real (`DEEPSEEK_API_KEY`).
- **Enriquecimiento con Last.fm real**: requiere `LASTFM_API_KEY` para poblar
  `commerciality_score`/`tags`/similares con datos reales.
