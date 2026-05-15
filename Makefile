# Auto-load .env via shell sourcing (NOT `include .env`).
# GNU make treats `#` as comment, which corrupts values like passwords with `#`.
# Bash sourcing handles `#` correctly inside a value when there's no space before it.
LOAD_ENV := if [ -f ./.env ]; then set -a; . ./.env; set +a; fi;

DB := $(PWD)/data/wsbonos.sqlite3

.PHONY: api ingest-stream health docker-up docker-down docker-logs migrate-ticks probe-symbols

api:
	@$(LOAD_ENV) DB_PATH="$(DB)" python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload

ingest-stream:
	@$(LOAD_ENV) DB_PATH="$(DB)" python3 -m ingestors.runner

health:
	@curl -sS http://127.0.0.1:8010/health && echo

docker-up:
	@docker compose up --build -d

docker-down:
	@docker compose down

docker-logs:
	@docker compose logs -f

migrate-ticks:
	@$(LOAD_ENV) DB_PATH="$(DB)" python3 db/migrations/001_split_ticks.py

probe-symbols:
	@$(LOAD_ENV) python3 scripts/probe_symbols.py $(SYMBOLS)
