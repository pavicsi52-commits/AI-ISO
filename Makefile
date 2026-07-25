.DEFAULT_GOAL := help
.PHONY: help setup up down restart logs dev-gateway dev-frontend \
	lint lint-backend lint-frontend format security \
	test test-backend test-frontend test-e2e build clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install all backend and frontend dependencies
	uv sync --all-packages
	pnpm install

up: ## Start the infrastructure stack (Postgres, Redis, RabbitMQ, Neo4j, MinIO, OpenSearch, Prometheus, Grafana)
	docker compose up -d

down: ## Stop the infrastructure stack
	docker compose down

restart: down up ## Restart the infrastructure stack

logs: ## Tail infrastructure logs
	docker compose logs -f

dev-gateway: ## Run the gateway service locally with reload
	cd services/gateway && uv run python -m uvicorn main:app --reload

dev-frontend: ## Run the frontend locally
	cd apps/frontend && pnpm dev

lint: lint-backend lint-frontend ## Run all linters

lint-backend: ## Lint and type-check the backend
	uv run ruff check .
	uv run black --check .
	uv run mypy services/gateway/app services/gateway/main.py

lint-frontend: ## Lint and type-check the frontend
	pnpm --filter frontend lint
	pnpm --filter frontend format:check
	pnpm --filter frontend typecheck

format: ## Auto-format backend and frontend code
	uv run black .
	uv run ruff check --fix .
	pnpm --filter frontend format

security: ## Run security scans (Bandit, pip-audit)
	uv run bandit -r services/gateway/app services/gateway/main.py
	uv run pip-audit --strict

test: test-backend test-frontend ## Run all test suites

test-backend: ## Run backend tests with coverage
	cd services/gateway && uv run pytest --cov=app --cov-report=term-missing

test-frontend: ## Run frontend tests with coverage
	pnpm --filter frontend test:coverage

test-e2e: ## Run frontend end-to-end tests (requires `pnpm exec playwright install`)
	pnpm --filter frontend test:e2e

build: ## Build all service and app Docker images
	docker build -f services/gateway/Dockerfile -t aiios/gateway:latest .
	docker build -f apps/frontend/Dockerfile -t aiios/frontend:latest .

clean: ## Remove build artifacts and caches
	find . -type d -name "__pycache__" -not -path "*/node_modules/*" -prune -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -not -path "*/node_modules/*" -prune -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -not -path "*/node_modules/*" -prune -exec rm -rf {} +
	rm -rf apps/frontend/.next apps/frontend/coverage apps/frontend/playwright-report apps/frontend/test-results
