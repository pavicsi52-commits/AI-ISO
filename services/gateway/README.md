# Gateway Service

The platform entry point. In this foundation phase (Prompt 011) it exposes
only health/readiness/liveness/metrics and OpenAPI documentation — no
business or routing logic yet.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt).
Folders such as `app/models`, `app/repositories`, `app/services`,
`app/security`, `app/events`, `app/workers`, `app/tasks`, `app/clients`, and
`app/validators` are reserved (each contains a `README.md` explaining why)
and populated as the gateway takes on real responsibilities (JWT
verification via `packages/shared-core/security`, request routing to
business services, rate limiting, etc.).

`app/config/settings.py` and `app/core/logging.py` are **temporary,
service-local implementations**. Once `packages/shared-core/config` (Prompt
013) and `packages/shared-core/logging` (Prompt 014) exist, this service
must be migrated to use them instead, per the "no duplicate implementation"
rule in `docs/012_Shared_Core_Framework.md.txt`.

## Running Locally

```bash
uv sync
uv run uvicorn main:app --reload
# If the uvicorn launcher is blocked by a local Application Control policy,
# see CONTRIBUTING.md "Known Environment Issues" and use:
uv run python -m uvicorn main:app --reload
```

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Overall service health |
| `GET /readiness` | Ready to receive traffic |
| `GET /liveness` | Process is alive |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` | OpenAPI (Swagger UI) |
| `GET /openapi.json` | OpenAPI schema |

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

## Docker

Build from the **repository root** (this service is a uv workspace member
and its lockfile resolves against the whole workspace):

```bash
docker build -f services/gateway/Dockerfile -t aiios/gateway .
```

## Troubleshooting

- **Settings fail to load**: confirm `AIIOS_*` environment variables are set
  or a `.env` file is present; see `.env.example` at the repository root.
- **`/readiness` returns `not_ready`**: the foundation-phase gateway only
  checks that configuration loaded; a `failed` check indicates
  `AIIOS_APP_NAME` resolved empty.
