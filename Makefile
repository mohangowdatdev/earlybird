# Earlybird. Run `make help` for targets. All Python runs through uv.
.DEFAULT_GOAL := help
.PHONY: help setup lint fmt test check reset

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

reset: ## DANGEROUS: delete var/ (local DB, tracker, notes, logs)
	@printf "This permanently deletes var/ (your local DB, tracker and notes).\nType 'earlybird' to confirm: "; \
	read answer; [ "$$answer" = "earlybird" ] || { echo "Aborted."; exit 1; }
	rm -rf var
	@echo "var/ deleted."
