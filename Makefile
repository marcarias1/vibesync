# VibeSync — targets de desarrollo.
# Usa el intérprete del venv (.venv) y asume Mongo local vía MONGO_URI.

PY := .venv/bin/python

.PHONY: install mongo-up test run lint

## Instala el paquete + extras de dev en el venv (añade ,ml para BGE-M3 real).
install:
	uv pip install --python $(PY) -e ".[dev]"

## Levanta MongoDB local (Atlas local: RS single-node + mongot para vector search).
## Requiere Docker. Alternativa: un mongod local escuchando en MONGO_URI.
mongo-up:
	docker compose up -d

## Ejecuta la suite (los tests que necesitan Mongo se saltan si no hay servidor).
test:
	PYTHONPATH=. $(PY) -m pytest tests -q

## Arranca la API con reload en http://127.0.0.1:8000 (healthcheck: /health).
run:
	$(PY) -m uvicorn app.main:app --reload

## Linter.
lint:
	ruff check app tests
