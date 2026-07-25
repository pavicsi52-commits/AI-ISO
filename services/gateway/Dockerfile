# syntax=docker/dockerfile:1
#
# Build context MUST be the repository root, e.g.:
#   docker build -f services/gateway/Dockerfile -t aiios/gateway .
#
# This is required because the gateway is a member of the root uv workspace
# (see /pyproject.toml [tool.uv.workspace]) and its lockfile is resolved
# against the whole workspace, per docs/004_Master_Repository_Structure.md.txt.

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/services/gateway/.venv

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY services/gateway/pyproject.toml services/gateway/pyproject.toml
# The gateway depends on packages/shared-core as a workspace path dependency
# (see services/gateway/pyproject.toml [tool.uv.sources]), so its full source
# -- not just its pyproject.toml -- must be present before `uv sync` can
# resolve and install it; unlike a registry dependency, there's no cached
# wheel uv can fall back to.
COPY packages/shared-core/ packages/shared-core/

WORKDIR /app/services/gateway
RUN uv sync --no-dev

COPY services/gateway/ .
RUN uv sync --no-dev

RUN useradd --create-home --uid 1000 aiios \
    && chown -R aiios:aiios /app
USER aiios

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
