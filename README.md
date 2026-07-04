# VibeSync — AI Smart Playlist Generator

Agente DJ predictivo para Spotify. Backend async (FastAPI + MongoDB + DeepSeek V4 Flash).

> **Arquitectura 2026:** Spotify recortó su API (feb-2026), así que Spotify se usa solo para
> OAuth + ingesta del histórico GDPR + escritura de playlists. La *inteligencia* (comercialidad,
> géneros, similitud, vibe) viene de **Last.fm + MusicBrainz + embeddings locales (BGE-M3) +
> MongoDB Vector Search**. Stack ~100% gratis; único coste: DeepSeek (céntimos).

## Estado
Backend funcional end-to-end **sin claves externas**, con ~40+ tests en verde:

- ✅ Scaffold, Docker (Atlas local), conexión async (`AsyncMongoClient`), modelos Pydantic v2, índices (incl. vectorial).
- ✅ Importador del `Streaming_History_Audio_*.json` (idempotente) + recálculo en background: counts → stats cache → seeding de `tracks` (embeddings + `play_count` + denormalización de `commerciality_score`/`tags`).
- ✅ Enriquecimiento (Last.fm + MusicBrainz + BGE-M3), filtro anti-comerciales v2 aplicado en el executor `find_similar_underground_tracks`.
- ✅ Búsqueda semántica **`$vectorSearch` real** contra atlas-local + embeddings BGE-M3 reales (ver `scripts/verify_semantic.py`).
- ✅ Spotify OAuth **PKCE** montado (`/auth/login`, `/auth/callback`; refresh token cifrado con Fernet) + escritura de playlists.
- ✅ Agente DeepSeek con tool-loop (probado con `FakeLLM`), executors de producción cableados (db/embedder/lastfm/spotify).
- ✅ Scheduler APScheduler (`refresh_stats` cada 6h) arrancado en el lifespan.

**Pendiente:** solo lo que requiere claves/login reales — `DEEPSEEK_API_KEY` (agente contra el LLM real), login OAuth de Spotify con `SPOTIFY_CLIENT_ID`, y `LASTFM_API_KEY`.

## Arranque
```bash
# 1. Levantar Mongo local con Vector Search (single-node RS + mongot)
docker compose up -d             # expone Mongo en el host en el puerto 27020

# 2. Entorno Python
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # core + dev  (añade ",ml" para BGE-M3 real)

# 3. Config
cp .env.example .env             # y rellenar claves + FERNET_KEY

# 4. Arrancar API
uvicorn app.main:app --reload
# healthcheck:
curl http://127.0.0.1:8000/health
```
