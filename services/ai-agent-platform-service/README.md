# AI-IOS Enterprise AI Agent Platform Service

Prompt 060. Multi-agent orchestration, LangGraph-style workflow
persistence with human-in-the-loop approval, an MCP client and server,
multi-provider model routing, a permission-aware tool registry and
execution stack, scoped agent memory, eight reasoning modes,
guardrails, sandboxing, and evaluation/benchmarking.

Runs on port **8031** against database **`aiios_ai_agent_platform`**
and Redis **db 33**.

---

## What this service is

An *agent* here is both a definition and its only instance. Unlike
`plugin-marketplace-service`'s own `Plugin`/`PluginInstallation` split
(Prompt 059), docs/060's own 17-table list has no separate installation
table — so one organization's own `Agent` row is the thing that is
registered, configured, versioned, activated, executed, paused, and
retired. `AgentMarketplaceEntry` publishes a listing *for* an agent; it
does not create a second installable copy of it.

### Reused frameworks vs genuine gaps

Established by a research pass before any code was written:

- **Reused directly:** `shared_core.workflow` — the real
  `WorkflowEngine`/`NodeExecutor`/`compile_workflow`/`parse_dict`
  pipeline and its `ApprovalRequest`/`ApprovalDecision` types back every
  multi-agent workflow run; `shared_core.scheduler` (all four
  leader-elected workers); `shared_core.events` (the nine domain
  events); `shared_core.telemetry.ai.trace_ai_request`/
  `trace_model_inference` (reused verbatim for "Model Calls" rather than
  reinvented); `shared_core.enums.health_status.HealthStatus`;
  `shared_core.queue.priority`'s five levels, adopted as `TaskPriority`'s
  literal column values.
- **Genuine gaps, built new:** per-request risk classification
  ([`app/guardrails/risk.py`](app/guardrails/risk.py)) — nothing else in
  this platform scores risk per request, as distinct from
  `policy-engine-service`'s own static per-policy `risk_weight`; a
  DB-backed checkpoint store ([`app/langgraph/`](app/langgraph/)), since
  `shared_core.workflow.checkpoint.CheckpointStore` is explicitly
  in-process-only by its own docstring; an MCP JSON-RPC client and
  server ([`app/mcp/`](app/mcp/)), which has no precedent anywhere in the
  monorepo; a four-strategy model router
  ([`app/routing/engine.py`](app/routing/engine.py)); an agent-shaped
  `PermissionCategory` taxonomy, since neither
  `shared_core.plugins.permissions.PluginPermission` nor
  plugin-marketplace-service's own category enum describes tool
  invocation, delegation, or model access.

### Two things the SDK genuinely cannot do, documented rather than papered over

**Resuming re-runs the whole graph from `START`.**
`WorkflowEngine.run()` always constructs a fresh, empty
`WorkflowExecution` and never calls `CheckpointStore.restore()` —
confirmed by reading its source. There is no sanctioned way to resume
only from the paused node forward, so
[`app/langgraph/approval.py`](app/langgraph/approval.py)'s own module
docstring states that limit plainly instead of pretending otherwise.

**A persisted checkpoint always reads `state: "running"`, even on a
completed run.** The engine saves each checkpoint *inside* its
per-level loop and transitions to `COMPLETED` only after that loop
exits, so the last checkpoint is by construction a mid-run snapshot.
The terminal state lives on the row's own `status` column — which is
what the checkpoint-recovery sweep actually filters on.

### The sandbox reuses the idea, not the code

[`app/sandbox/`](app/sandbox/) mirrors
`shared_core.plugins.sandbox.SandboxPolicy`'s shape but is keyed to
this service's own `PermissionCategory` rather than
`PluginPermission` — the same "don't force an enum bridge between
partially-overlapping vocabularies" call Prompt 059 already made. A
plugin's vocabulary (filesystem, network, database, secrets) and an
agent's (tool invocation, delegation, model access, memory access) only
partly overlap.

`cpu_limit_seconds` is **declared and reported, not enforced**: no
in-process Python sandbox can cap CPU time without an OS or container
boundary underneath it, and `resource.setrlimit` does not exist on
Windows at all. The field is the policy a real deployment's own
boundary gets configured from.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/models/`](app/models/) | 17 tables |
| [`app/guardrails/`](app/guardrails/) | Redaction, input/output screening, injection detection, per-request risk classification |
| [`app/sandbox/`](app/sandbox/) | Policy, permission/filesystem/network checks, real `create_subprocess_exec` isolation |
| [`app/tool_registry/`](app/tool_registry/) | Four-layer fail-closed `authorize()` + JSON-schema `validate_arguments()` |
| [`app/tool_execution/`](app/tool_execution/) | Executor + the eight concrete tool-kind handlers |
| [`app/clients/`](app/clients/) | Four provider clients covering eight `ModelProvider` values (`OpenAiCompatibleClient` serves OpenAI/Azure/vLLM/Local/OpenRouter), the routing-aware `ModelRegistry`, plus Automation and Policy Engine clients |
| [`app/routing/`](app/routing/) | Rule-based / cost-aware / latency-aware / fallback chain resolution |
| [`app/memory/`](app/memory/) | Six-scope agent memory with precedence and live expiry |
| [`app/reasoning/`](app/reasoning/) | Seven reasoning-mode runners (Chain-of-Thought is "internal only" — a plain call, by design) |
| [`app/agents/`](app/agents/) | Orchestrator + the six multi-agent coordination patterns |
| [`app/langgraph/`](app/langgraph/) | DB-persisted checkpointing, AI/approval node handlers, workflow + approval services |
| [`app/mcp/`](app/mcp/) | JSON-RPC 2.0 protocol types, transport-agnostic server, session-aware client |
| [`app/evaluation/`](app/evaluation/) · [`app/benchmarks/`](app/benchmarks/) | Five scorers; case/suite runner and persistence |
| [`app/repositories/`](app/repositories/) | 14 modules, 17 repositories — `require_in_org` named apart from the base's unscoped `require_by_id` |
| [`app/services/`](app/services/) | Agent lifecycle, tasks, tools, execution, reporting/audit, handler wiring |
| [`app/api/`](app/api/) | 20 routes — the 16 literal docs/060 endpoints under `/agents/*`, plus health/liveness/readiness/metrics |
| [`app/workers/`](app/workers/) | Task dispatch, checkpoint recovery, statistics rollup, benchmark sweep — all leader-elected |

### The router-registration order matters

[`app/api/agents.py`](app/api/agents.py) registers every static-segment
route (`/tasks`, `/tools`, `/evaluations`, `/benchmarks`, `/statistics`,
`/reports`) *before* the `GET/PUT/DELETE /{agent_id}` catch-all.
FastAPI/Starlette matches in registration order, so declared the other
way round, `GET /agents/tasks` would be hijacked into `get_agent` with
`agent_id="tasks"` and fail UUID parsing before ever reaching the
handler that owns that path. The same bug class already found and fixed
in notification-center-service and plugin-marketplace-service; guarded
here by construction and covered by an explicit regression test.

---

## Running it

```bash
docker build -t aiios/ai-agent-platform-service:0.1.0 \
  -f services/ai-agent-platform-service/Dockerfile .

MSYS_NO_PATHCONV=1 docker run -d --name aiios_ai_agent_platform \
  --network aiios_aiios_network -p 8031:8031 \
  -e AIIOS_DATABASE_HOST=aiios_postgres -e AIIOS_DATABASE_PORT=5432 \
  -e AIIOS_DATABASE_NAME=aiios_ai_agent_platform \
  -e AIIOS_DATABASE_USER=aiios -e AIIOS_DATABASE_PASSWORD=change-me \
  -e AIIOS_REDIS_HOST=aiios_redis -e AIIOS_REDIS_DB=33 \
  -e AIIOS_REDIS_PASSWORD=change-me \
  -e AIIOS_RABBITMQ_HOST=aiios_rabbitmq -e AIIOS_RABBITMQ_USER=aiios \
  -e AIIOS_RABBITMQ_PASSWORD=change-me -e AIIOS_RABBITMQ_VHOST=/aiios \
  -e AIIOS_NEO4J_HOST=aiios_neo4j -e AIIOS_NEO4J_USER=neo4j \
  -e AIIOS_NEO4J_PASSWORD=change-me-min-8-chars \
  aiios/ai-agent-platform-service:0.1.0
```

Migrations: `uv run alembic upgrade head`. `keys/jwt_public_key.pem` is
the public half of `services/authentication-service`'s signing key —
this service verifies tokens but never issues them.

**`MSYS_NO_PATHCONV=1` is required on any `docker run` whose arguments
contain a leading `/`** (here, `AIIOS_RABBITMQ_VHOST=/aiios`). Git Bash
on Windows otherwise silently rewrites it into a Windows path before
Docker ever sees it, producing an opaque `AMQPInternalError` at
connection time with no hint that the vhost was mangled.

### Model providers are configured, never stored

`agents`/`agent_profiles` reference a provider by name only. The
credential comes from `AIIOS_AI_AGENT_PLATFORM_SERVICE_<PROVIDER>_API_KEY`
or a live secret reference at call time — never the database. A
provider with no credential configured is **not registered at all**, so
asking for it fails with a clear "not configured" error rather than a
confusing 401 from the vendor. Ollama, vLLM, and Local need no
credential; their reachability is discovered at call time.

### Workers, verified firing on their own

All four workers were verified against the real stack by seeding a due
task and a stuck-running workflow, starting a real `SchedulerManager`,
and then **only polling** — never calling `tick()` by hand. Checkpoint
recovery resumed the stuck workflow to `completed` at +3s; task dispatch
reached a real model-provider call and retried per policy at +9s;
statistics rollup produced its row at +60s; the benchmark sweep produced
its row at +66s. This is the same "does the worker actually fire without
being manually triggered" check webhook-service's own Prompt 057 build
established and every service since has reproduced. Seeded rows were
deleted from all six affected tables afterwards.

---

## Tests

**1332 tests, 97.84% branch coverage** against real PostgreSQL, Redis,
RabbitMQ, and Neo4j. Nothing here mocks infrastructure.

```bash
uv run python -m pytest -q --cov=app --cov-report=term-missing
```

### Outbound model calls are real, and expected to fail

No local Ollama/vLLM backend is guaranteed in every environment this
suite runs in, so `ModelRegistry.chat()` genuinely raising "every
provider in the chain failed" is an **accepted, correct** test outcome.
What those tests verify is that this service's own dispatch, guardrail,
memory, and persistence logic behaved correctly around that real
failure — not that an LLM answered. Assertions are written to hold on
whichever real outcome occurs.

### Neo4j has no SAVEPOINT

PostgreSQL tests are SAVEPOINT-isolated and roll back automatically.
Graph-touching tests must clean up their own nodes explicitly — the same
limitation `knowledge-graph-service`'s own conftest documents.

### `app/telemetry/tracing.py` has its own dedicated test file

No service or worker call site is wired to the `trace_*` helpers yet, so
without a standalone `tests/test_telemetry.py` the module would sit at
0%. It uses a real `TracerProvider` with `InMemorySpanExporter` — a real
OTel SDK component, not a mock — so a future `attributes={...}`
regression (the confirmed repo-wide defect class this module's own
docstring warns about) would be caught for real.

---

## Notes worth keeping

- **`AgentMemory` deliberately has no DB-level uniqueness.** The
  original `UniqueConstraint("agent_id", "scope", "key")` was too narrow
  — it ignored `task_id`/`session_id`, and PostgreSQL treats NULLs as
  distinct anyway, so it would not have enforced what it appeared to.
  Dropped in favour of service-level soft uniqueness, matching
  `AiMemory`'s own established precedent.
- **Enum columns are plain `str` at runtime.** There is no SQLAlchemy
  `Enum` column type anywhere in this codebase, so a loaded row's
  enum-typed attribute compares with `==`, never `is`.
- **JSON list columns are reassigned, never mutated in place**
  (`obj.field = [*obj.field, new]`), matching the platform-wide pattern.
- **`start_span` takes `**attributes`, not an `attributes=` keyword.**
  Passing one silently drops every attribute rather than raising — a
  confirmed repo-wide defect in services built before Prompt 054. This
  service's own `tracing.py` was written correct from the start.
- **Spans carry identifiers and outcomes, never prompts, model output,
  or memory content.** An agent's request/response and remembered facts
  can carry tenant data, and a tracing backend has different retention
  and access rules than this service's own database.
- **`AutomationClient` now honours its own error contract.** A sibling
  service answering with the right status code but an unreadable body
  (version skew, or a proxy substituting its own page) used to escape as
  a raw `KeyError`; it now surfaces as `DependencyError` like every other
  failure mode in that client. Found by the test-writing pass.

---

## What's deliberately out of scope

- **Chain-of-Thought has no dedicated runner.** docs/060 calls it
  "internal only", so it is a single plain model call rather than a
  separate multi-step loop pretending to be one.
- **`ReportService` builds only `USAGE`, `EXECUTION`, and `AUDIT`.**
  The other four kinds return `{"rows": []}` with status `COMPLETED` —
  the same first-cut scope decision every prior AI-IOS `ReportService`
  made.
- **No real OpenTelemetry `TracerProvider` is wired into the app
  factory.** A repo-wide grep confirmed no AI-IOS service does this yet;
  every service's `tracing.py` takes a `Tracer` parameter that is, in
  current practice, never populated from a real SDK provider. This
  service follows that precedent rather than diverging alone.
