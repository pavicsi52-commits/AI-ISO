# Frontend

The AI-IOS web client. In this foundation phase (Prompt 011) it contains a
single placeholder dashboard that proves the platform's presentation layer
works end-to-end against the gateway — no business modules yet.

## Architecture

Structure per
[`docs/009_Frontend_Master_Architecture.md.txt`](../../docs/009_Frontend_Master_Architecture.md.txt)
and design tokens per
[`docs/010_UI_UX_Design_System_Master.md.txt`](../../docs/010_UI_UX_Design_System_Master.md.txt).

- `app/` — Next.js App Router routes only; no business logic.
- `components/` — reusable, presentation-only UI primitives (`ui`, `layout`, `cards`, `feedback`, ...).
- `modules/` — feature modules (e.g. `dashboard`), each owning its own `components/hooks/services/types`.
- `services/` — the only place allowed to call `fetch()`. See `services/api-client.ts`.
- `stores/` — Zustand global state (e.g. theme).
- `providers/` — React context providers composed once in `app/layout.tsx`.
- `config/` — centralized environment access. See the note in `config/env.ts` about `NEXT_PUBLIC_*` variables requiring static access for Next.js to inline them into the browser bundle.

## Running Locally

```bash
pnpm install
pnpm dev
```

Requires the gateway service running (see `services/gateway/README.md`) and
`NEXT_PUBLIC_API_BASE_URL` pointing at it (defaults to `http://localhost:8000`,
see `.env.example` at the repository root).

## Testing

```bash
pnpm typecheck
pnpm lint
pnpm test              # unit tests (Vitest + Testing Library)
pnpm test:coverage
pnpm test:e2e           # Playwright, requires `pnpm exec playwright install`
```

## Docker

Build from the **repository root** (this app is a pnpm workspace member and
its lockfile resolves against the whole workspace):

```bash
docker build -f apps/frontend/Dockerfile -t aiios/frontend .
```
