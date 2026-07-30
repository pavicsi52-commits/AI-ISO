# syntax=docker/dockerfile:1
#
# Build context MUST be the repository root, e.g.:
#   docker build -f services/knowledge-graph-service/Dockerfile -t aiios/knowledge-graph-service .
#
# This is required because the knowledge graph service is a member of
# the root uv workspace (see /pyproject.toml [tool.uv.workspace]) and its
# lockfile is resolved against the whole workspace, per
# docs/004_Master_Repository_Structure.md.txt.

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/services/knowledge-graph-service/.venv

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# curl for the container HEALTHCHECK only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY services/knowledge-graph-service/pyproject.toml services/knowledge-graph-service/pyproject.toml
# This service depends on packages/shared-core as a workspace path
# dependency (see services/knowledge-graph-service/pyproject.toml
# [tool.uv.sources]), so its full source -- not just its pyproject.toml
# -- must be present before `uv sync` can resolve and install it;
# unlike a registry dependency, there's no cached wheel uv can fall
# back to.
COPY packages/shared-core/ packages/shared-core/

WORKDIR /app/services/knowledge-graph-service
RUN uv sync --no-dev

COPY services/knowledge-graph-service/ .
RUN uv sync --no-dev

RUN useradd --create-home --uid 1000 aiios \
    && chown -R aiios:aiios /app
USER aiios

EXPOSE 8020

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
    CMD curl -sf http://localhost:8020/health || exit 1

# Migrations are applied as a separate step (`uv run alembic upgrade
# head`) ahead of starting the container in every real deployment -- not
# baked into CMD -- so a multi-replica rollout never races two containers
# running the same migration concurrently.
#
# The graph schema (Neo4j constraints and indexes) is applied at startup
# instead, by the application factory: every statement is IF NOT EXISTS,
# so unlike a relational migration it is genuinely idempotent and safe
# for N replicas to run concurrently.
#
# The statistics rollup is **leader-elected** through
# shared_core.scheduler (see app/workers/registrar.py), so every replica
# starts identically -- no replica needs special flags to be the
# "worker" one, and only one of them will actually compute the rollup.
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020"]
