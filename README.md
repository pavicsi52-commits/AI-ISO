# AI Infrastructure Operating System (AI-IOS)

AI-IOS is an enterprise Infrastructure Operating System for discovering, managing,
automating, validating, monitoring, and operating modern IT infrastructure using
Artificial Intelligence. It is not an automation UI wrapper — it is an original,
API-first, event-driven microservices platform.

See [`docs/`](docs/) for the full frozen specification set (`001`–`020`) that
governs this repository's architecture, technology stack, coding standards, and
implementation order.

## Status

Platform foundation (Prompt 011) and the Enterprise Shared Core Framework
(Prompts 012–020) are under active implementation. No business services exist
yet — see [`ROADMAP.md`](ROADMAP.md).

## Repository Layout

| Path | Purpose |
|---|---|
| `apps/` | Client applications (`frontend`, future `admin`, `mobile`, `desktop`) |
| `services/` | Independently deployable microservices |
| `packages/shared-core/` | Reusable enterprise framework every service depends on |
| `infrastructure/` | Docker, Kubernetes, Helm, Terraform, Ansible, and datastore configuration |
| `database/` | Cross-cutting migrations, seeds, fixtures |
| `docs/` | Specification and architecture documentation |
| `scripts/` | Bootstrap, development, deployment, and maintenance scripts |
| `tests/` | Cross-service integration, performance, security, e2e, and load tests |
| `tools/` | Internal CLI, codegen, and developer tooling |
| `configs/` | Per-environment configuration |
| `templates/` | Email, report, notification, workflow, and playbook templates |

## Technology Stack

Frontend: Next.js (App Router), TypeScript, TailwindCSS, Zustand, TanStack Query.
Backend: FastAPI, Python 3.13+, SQLAlchemy 2.x, Pydantic v2. Data: PostgreSQL,
Redis, RabbitMQ, Neo4j, MinIO, OpenSearch. See
[`docs/003_Technology_Stack_Master.md.txt`](docs/003_Technology_Stack_Master.md.txt)
for the complete, frozen stack.

## Getting Started

```bash
# Start the infrastructure stack (Postgres, Redis, RabbitMQ, Neo4j, MinIO, OpenSearch, Prometheus, Grafana)
docker compose up -d

# Backend (gateway service)
cd services/gateway
uv sync
uv run uvicorn app.main:app --reload

# Frontend
cd apps/frontend
pnpm install
pnpm dev
```

## Development

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch strategy, commit conventions,
and the pull request process. See
[`docs/005_Coding_Standards_Master.md.txt`](docs/005_Coding_Standards_Master.md.txt)
for coding standards, which are binding for every module in this repository.

## Security

See [`SECURITY.md`](SECURITY.md) for how to report a vulnerability.

## License

Proprietary. See [`LICENSE`](LICENSE).
