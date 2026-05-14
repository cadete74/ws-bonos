# Auto-load .env if present (Veta creds and other config live there).
# Shell env vars still take precedence per GNU make rules.
ifneq (,$(wildcard ./.env))
    include .env
    export
endif

DB := $(PWD)/data/wsbonos.sqlite3

.PHONY: api ingest-once ingest-loop health docker-up docker-down docker-logs

api:
	@DB_PATH="$(DB)" python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload

ingest-once:
	@DB_PATH="$(DB)" python3 -m ingestors.runner --once

ingest-loop:
	@DB_PATH="$(DB)" bash -lc 'while :; do python3 -m ingestors.runner --once || true; sleep 10; done'

health:
	@curl -sS http://127.0.0.1:8010/health && echo

docker-up:
	@docker compose up --build -d

docker-down:
	@docker compose down

docker-logs:
	@docker compose logs -f
