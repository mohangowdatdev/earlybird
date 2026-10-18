# Earlybird. Run `make help` for targets. All Python runs through uv.
.DEFAULT_GOAL := help
.PHONY: help setup lint fmt test check up down restart status logs sync ingest db reset

RUN := var/run
LOGS := var/logs
PIDFILE := $(RUN)/earlybird.pid
PORT ?= $(or $(EARLYBIRD_PORTAL_PORT),8765)

help: ## Show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

setup: ## Install dependencies and git hooks
	uv sync
	uv run pre-commit install

lint: ## ruff, mypy, import contracts, registry schema
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run lint-imports
	uv run check-jsonschema --schemafile registry/schema.json registry/companies.yaml

fmt: ## Format and autofix
	uv run ruff format .
	uv run ruff check --fix .

test: ## Run tests
	uv run pytest

check: lint test ## Everything CI runs (except gitleaks)

db: ## Create or migrate the local database
	uv run earlybird db upgrade

up: db ## Start portal + scheduler in the background (http://127.0.0.1:8765)
	@mkdir -p $(RUN) $(LOGS)
	@if [ -f $(PIDFILE) ] && kill -0 $$(cat $(PIDFILE)) 2>/dev/null; then \
		echo "Earlybird is already running (pid $$(cat $(PIDFILE)))."; \
	else \
		rm -f $(PIDFILE); \
		nohup .venv/bin/honcho start -f Procfile >> $(LOGS)/earlybird.log 2>&1 & echo $$! > $(PIDFILE); \
		sleep 2; \
		if kill -0 $$(cat $(PIDFILE)) 2>/dev/null; then \
			echo "Earlybird is up: http://127.0.0.1:$(PORT)  (logs: make logs, stop: make down)"; \
		else \
			echo "Earlybird failed to start; see $(LOGS)/earlybird.log"; rm -f $(PIDFILE); exit 1; \
		fi; \
	fi

down: ## Stop everything (data in var/ is kept)
	@if [ -f $(PIDFILE) ] && kill -0 $$(cat $(PIDFILE)) 2>/dev/null; then \
		kill $$(cat $(PIDFILE)); \
		for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 $$(cat $(PIDFILE)) 2>/dev/null || break; sleep 0.5; done; \
		echo "Earlybird stopped."; \
	else \
		echo "Earlybird is not running."; \
	fi
	@rm -f $(PIDFILE)

restart: down up ## Restart

status: ## Is it running?
	@if [ -f $(PIDFILE) ] && kill -0 $$(cat $(PIDFILE)) 2>/dev/null; then echo "running (pid $$(cat $(PIDFILE)))"; else echo "stopped"; fi

logs: ## Follow the logs
	@mkdir -p $(LOGS) && touch $(LOGS)/earlybird.log && tail -n 100 -f $(LOGS)/earlybird.log

sync: db ## Pull the latest public dataset into the local DB
	uv run earlybird sync

ingest: ## Run a full ingestion locally into var/state.db (debugging the public plane)
	uv run earlybird ingest --db var/state.db

reset: ## DANGEROUS: delete var/ (local DB, tracker, notes, logs)
	@printf "This permanently deletes var/ (your local DB, tracker and notes).\nType 'earlybird' to confirm: "; \
	read answer; [ "$$answer" = "earlybird" ] || { echo "Aborted."; exit 1; }
	@$(MAKE) --no-print-directory down
	rm -rf var
	@echo "var/ deleted."
