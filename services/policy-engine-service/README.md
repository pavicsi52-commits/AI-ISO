# AI-IOS Policy Engine Service

Prompt 050. The platform's authorization authority: ABAC/RBAC policy
authoring with a reviewed lifecycle, a pure evaluation engine, quotas,
approvals, time-bounded exceptions, compliance violations, what-if
simulation, an append-only audit trail, and statistics.

Runs on port **8021** against database **`aiios_policy_engine`**, Redis
**db 23**, and **RabbitMQ**.

---

## What this service is

Every protected operation anywhere on the platform ends up asking this
service one question: *may this subject do this action to this
resource?* That single fact shapes every trade-off below.

It means this service is **in the latency path of everything**, so it
answers from compiled rules and never calls out mid-decision. It means
**its availability is the platform's availability**, so several paths
here degrade rather than fail. And it means **a wrong answer is not a
bug in one feature** — a wrongly permissive one is a breach, a wrongly
restrictive one is an outage.

### The engine is pure

[`app/evaluation/engine.py`](app/evaluation/engine.py) has no database,
no network, and no clock it did not receive as an argument. It takes a
catalogue of `EvaluablePolicy` and an `EvaluationContext` and returns a
`Decision`. Everything that touches infrastructure lives in
[`app/services/decision.py`](app/services/decision.py) around it.

This is what makes the behaviour testable at all. 183 of the tests in
this package exercise the engine directly, at speed, with no fixtures —
which is the only way a decision table with nine effects and their
precedence gets covered honestly.

### Effect precedence is a table, not a chain of ifs

```python
EFFECT_PRECEDENCE: dict[PolicyEffect, int] = {
    PolicyEffect.ALLOW: 0,               PolicyEffect.CONDITIONAL_ALLOW: 1,
    PolicyEffect.REQUIRE_MFA: 2,         PolicyEffect.REQUIRE_APPROVAL: 3,
    PolicyEffect.ESCALATE: 4,            PolicyEffect.DEFERRED: 5,
    PolicyEffect.QUOTA_EXCEEDED: 6,      PolicyEffect.CONDITIONAL_DENY: 7,
    PolicyEffect.DENY: 8,
}
```

Combination takes the maximum. **Deny always wins**, and every
intermediate effect sits at a defined distance from both ends, so adding
a tenth effect is a line in a table rather than an edit to a conditional
somebody has to reason about at 03:00.

### Fail-closed, with the default stated out loud

`fail_closed=true` and `default_effect=deny` are startup-logged, because
they are the two settings that decide what happens when the service
knows nothing. **A request that matches no policy is refused.** That
makes a fresh organization refuse everything until its baseline is
seeded — which is the correct failure, and `POST /policies/guardrails/seed`
is how it gets fixed.

### Publishing is the only operation that changes live authorization

So it is the only place the review lifecycle can actually be enforced:

```
DRAFT ──▶ REVIEW ──▶ APPROVED ──▶ PUBLISHED
  ▲                                   │
  └───────────────────────────────────┘
```

`publish` requires **APPROVED**. Re-issuing a live policy goes back
around the loop — four calls to change a rule that is already refusing
people's work, deliberately.

This was broken until the live end-to-end run. `_ALLOWED_TRANSITIONS`
had always named DRAFT → PUBLISHED as the move that must be impossible,
but only `transition` consulted the table; `publish` performed exactly
that move while checking nothing but whether the policy was archived. A
lifecycle enforced on the door nobody needs and left off the one that
matters is not a lifecycle. See *Notes worth keeping* below for why no
test caught it.

### Rules are data, evaluated without `eval`

[`app/conditions/operators.py`](app/conditions/operators.py) implements
25 operators as ordinary functions over a dispatch table. Nothing in a
stored policy is ever executed as code.

- `MAX_PATTERN_LENGTH = 512` and `_MAX_MATCH_INPUT = 4096` bound the
  regex operators, because a policy author is a user like any other and
  a catastrophic pattern in an authorization rule stalls every decision
  on the platform.
- A missing attribute is `_MISSING`, distinct from `None`. `equals` on a
  missing attribute is false, not an error and not a match — an absent
  attribute must never satisfy a condition by accident.
- `time_between` parses ISO timestamps as well as times, because a
  maintenance-window policy receives a JSON timestamp and would
  otherwise silently never match.

**Conditions can compare two attributes**, via `value_source` /
`value_path`. This is the only way to express the central ABAC statement
— *the resource's organization must equal the subject's* — because no
literal means "whatever the caller's organization happens to be". A
missing right-hand side never matches.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/evaluation/`](app/evaluation/) | The pure engine: candidate selection, evaluation, combination |
| [`app/rules/`](app/rules/) | Rule trees, validation, `rule_from_dict` |
| [`app/conditions/`](app/conditions/) | The 25 operators |
| [`app/attributes/`](app/attributes/) | `EvaluationContext`, path resolution, the sensitive-path catalogue |
| [`app/publishing/`](app/publishing/) | Compilation, checksums, integrity verification, semantic versioning |
| [`app/quotas/`](app/quotas/) | Consumption budgets and period arithmetic |
| [`app/simulation/`](app/simulation/) | What-if comparison and conflict detection |
| [`app/guardrails/`](app/guardrails/) | The built-in baseline policies |
| [`app/models/`](app/models/) | 15 tables |
| [`app/repositories/`](app/repositories/) | 15 repositories |
| [`app/services/`](app/services/) | 9 services — the only layer that touches infrastructure |
| [`app/api/`](app/api/) | 43 operations across 36 paths |
| [`app/workers/`](app/workers/) | Statistics rollup, approval expiry sweep |

### `require_in_org`, not `require_by_id`

The tenant-scoped lookups are named differently from the base
repository's unscoped `require_by_id` on purpose. Two same-named methods
of different arity on one class make `require_by_id(exception_id)` look
correct when it is in fact a cross-tenant read. Every call site now says
which one it means.

---

## Running it

```bash
docker build -t aiios/policy-engine-service:0.1.0 \
  -f services/policy-engine-service/Dockerfile .

docker run -d --name aiios_policy_engine \
  --network aiios_aiios_network -p 8021:8021 \
  -e AIIOS_DATABASE_HOST=aiios_postgres -e AIIOS_DATABASE_PORT=5432 \
  -e AIIOS_DATABASE_NAME=aiios_policy_engine \
  -e AIIOS_DATABASE_USER=aiios -e AIIOS_DATABASE_PASSWORD=change-me \
  -e AIIOS_REDIS_HOST=aiios_redis -e AIIOS_REDIS_DB=23 \
  -e AIIOS_REDIS_PASSWORD=change-me \
  -e AIIOS_RABBITMQ_HOST=aiios_rabbitmq -e AIIOS_RABBITMQ_USER=aiios \
  -e AIIOS_RABBITMQ_PASSWORD=change-me -e AIIOS_RABBITMQ_VHOST=/aiios \
  -e AIIOS_APPLICATION_PORT=8021 \
  aiios/policy-engine-service:0.1.0
```

`GET /readiness` reports both PostgreSQL and Redis. Migrations:
`uv run alembic upgrade head`.

This service **verifies but never issues** JWTs — signing belongs to
`services/authentication-service`. `keys/jwt_public_key.pem` is the
public half of that service's keypair, and a missing key is a
`DependencyError` rather than an ephemeral fallback, because a service
that generates its own verification key verifies nothing.

---

## Tests

536 tests, **95.39%** branch coverage, against real PostgreSQL, Redis,
and RabbitMQ. No mocked infrastructure anywhere.

```bash
uv run python -m pytest -q --cov=app --cov-branch --cov-fail-under=95
```

The notification service in the fixtures is real, with **no channel
registered** — so every send genuinely fails, and every caller is
exercised against the failure it has to survive.

### The one thing the HTTP tests cannot tell you

The `app` fixture overrides only the request session, so a test's writes
roll back. That override changes **transaction lifetime**, which means
any behaviour that depends on transaction lifetime is untestable there.

Concretely: `AuditService.record_denied` commits in its own
`session_scope` precisely so a refused request's audit entry survives the
rollback of the request that raised. Under a SAVEPOINT that distinction
vanishes and the test passes either way. That path is therefore tested
at service level against the real session factory, never over HTTP.

**Where a test's isolation differs from production's, the test is only
trustworthy about things that isolation does not touch.**

---

## Notes worth keeping

- **A gate verified open is not a gate verified shut.** Every test
  walked DRAFT → REVIEW → APPROVED → publish correctly, so none of them
  ever tried publishing a draft — the illegal move stayed legal for the
  entire build. The conftest fixture's own comment claimed it was
  exercising "the lifecycle refusing a direct draft-to-published move"
  while doing nothing of the sort. Found by driving the real API against
  the built image.

- **Documenting a hazard is not avoiding it.** `Policy.version` was
  annotated `Mapped[str]` and shadowed the base entity's integer
  optimistic-lock `version`, so every write raised `TypeError: can only
  concatenate str (not "int") to str`. A docstring explaining why the
  collision could not happen is what created it. Now `semantic_version`.

- **A domain event that is not registered is a 400 for the caller.**
  `default_registry.register` on every event class, or the publisher
  refuses it and a correct policy write fails. The service-level tests
  missed this for the same reason they missed the lifecycle hole: they
  inject a recording publisher, so the real registry never runs.

- **A shared constraint expressed in two units gets violated by whoever
  does not know about the other one.** Carried over from Prompt 049,
  where a node ceiling was handed to four row-capped reads.

- **Simulation compiles drafts on the fly** rather than reading
  `compiled_rule`, which is only written at publish time. Reading the
  column would have made the entire draft-preview feature silently do
  nothing while reporting success.
