# Roadmap

AI-IOS is being built from a frozen, sequential specification set
(`docs/001`–`docs/020`, with further prompts to follow). Each phase below
corresponds to one or more specification documents and is only started once
the prior phase is complete and verified.

## Phase 0 — Specification (Prompts 001–010)

Product vision, master architecture, technology stack, repository structure,
coding standards, API design, database architecture, backend architecture,
frontend architecture, and UI/UX design system. Specification only — no code.
**Status: Complete.**

## Phase 1 — Platform Foundation (Prompt 011)

Monorepo bootstrap: root structure, Docker Compose infrastructure stack,
`services/gateway` foundation service (health/readiness/liveness/metrics only),
`apps/frontend` placeholder dashboard, CI/CD, pre-commit, and all quality
tooling. No business modules. **Status: In progress.**

## Phase 2 — Enterprise Shared Core Framework (Prompts 012–020)

A single reusable framework (`packages/shared-core/`) that every future
microservice depends on, so no business service duplicates cross-cutting
concerns:

- **012** Shared Core skeleton (constants, enums, base models, schemas, middleware, storage, telemetry, monitoring, decorators, helpers, interfaces, types)
- **013** Configuration Framework
- **014** Logging Framework
- **015** Exception Framework
- **016** Validation Framework
- **017** Security Framework
- **018** Database Framework
- **019** Cache Framework
- **020** Event Framework

**Status: Not started.**

## Phase 3 — Business Services (future prompts)

Authentication, organizations, projects, teams, inventory, asset discovery,
knowledge graph, automation, playbooks, execution, workflow, validation,
monitoring, alerting, notification, audit, reporting, settings, secrets,
scheduler, AI assistant, and license management services — each built on top
of the Phase 2 shared framework. Not yet specified.

## Phase 4 — Frontend Modules (future prompts)

Full enterprise UI built on the Phase 1 frontend foundation and the Phase 0
design system, module by module, mirroring the Phase 3 services.

## Phase 5+ — Enterprise Hardening (future prompts)

Marketplace, self-healing automation, disaster recovery workflows, and
replacing temporary dependencies (e.g. Grafana) with native dashboards, per
the long-term goals in
[`docs/001_Product_Vision.md.txt`](docs/001_Product_Vision.md.txt).
