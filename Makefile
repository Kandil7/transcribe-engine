.DEFAULT_GOAL := help
SHELL := /bin/bash
UV := uv run

.PHONY: help setup fmt lint typecheck imports test check itest cov eval up down migrate seed openapi ci autopilot dev demo

help: ## Show targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup: ## Install deps and git hooks
	uv sync --all-groups
	$(UV) pre-commit install --hook-type pre-commit --hook-type commit-msg || true

gpu-torch: ## Install the CUDA 12.6 torch build for this machine's Quadro RTX 5000 (D-073, local only)
	uv pip install --python .venv --index-url https://download.pytorch.org/whl/cu126 "torch==2.14.1"

gpu-check: ## Check that torch sees the GPU and computes a half-precision product correctly
	$(UV) python -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'; a=torch.ones(64,64,device='cuda',dtype=torch.float16); total=float((a@a).float().sum()); assert total == 64**3, total; print(torch.cuda.get_device_name(0), 'OK', total)"

fmt: ## Format and auto-fix
	$(UV) ruff format .
	$(UV) ruff check --fix .

lint:
	$(UV) ruff format --check .
	$(UV) ruff check .

typecheck:
	$(UV) mypy

imports:
	$(UV) lint-imports

test: ## Unit tests only (fast, no Docker)
	$(UV) pytest tests/unit -q -x -m "not integration and not gpu and not eval"

check: lint typecheck imports test ## Fast gate: must pass on every commit (< 60 s)

itest: ## Integration + contract tests (Docker)
	$(UV) pytest tests/integration tests/contracts -q -m "integration or contract"

cov: ## Unit + integration with coverage gate
	$(UV) pytest tests/unit tests/integration tests/contracts -q --cov --cov-report=term-missing

eval: ## Evaluation harness on the dev set (GPU)
	$(UV) python -m evaluation.run --split dev

up: ## Start Postgres (pgvector) + MinIO
	docker compose up -d --wait

down:
	docker compose down

migrate: ## Apply migrations to local DB
	$(UV) alembic upgrade head

ci: check cov ## What CI runs on every PR

autopilot: ## Build the project autonomously, one slice per run (see docs/AUTOPILOT.ar.md)
	scripts/autopilot.sh

seed: ## Create the local tenant and API key (printed once, saved to .env.local)
	uv run python scripts/seed.py

openapi: ## Regenerate docs/openapi.json from the code
	uv run python scripts/export_openapi.py

dev: ## Run the local stack: compose, migrations, API, cpu and gpu workers (Ctrl-C stops)
	uv run python scripts/dev.py

demo: ## Upload FILE, wait for the job, save out/<job>.json (needs make dev and TE_API_KEY)
	uv run python scripts/demo.py "$(FILE)"
