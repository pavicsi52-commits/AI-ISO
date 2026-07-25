# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Repository bootstrap: monorepo structure, Docker Compose infrastructure stack
  (PostgreSQL, Redis, RabbitMQ, Neo4j, MinIO, OpenSearch, Prometheus, Grafana),
  `services/gateway` foundation service, `apps/frontend` placeholder dashboard,
  CI pipeline, pre-commit hooks, and quality tooling (Ruff, Black, MyPy, Bandit,
  pip-audit, ESLint, Prettier, Vitest, Playwright).
