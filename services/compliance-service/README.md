# AI-IOS Compliance Service

Prompt 051. Continuous compliance assessment against regulatory
frameworks, security standards, and industrial safety standards:
control catalogues with cross-framework mappings, immutable evidence,
findings with age-preserving deduplication, time-bounded exceptions, a
derived risk register, remediation with re-assessment-gated
verification, weighted scoring, and an append-only audit trail.

Runs on port **8022** against database **`aiios_compliance`** and Redis
**db 24**.

---

## What this service is

Every score this service publishes ends up in a report somebody outside
engineering reads and acts on. That shapes every trade-off below: **a
wrong number is not a bug in one feature** — a falsely high score hides
risk from the people responsible for it, and a falsely low one spends
somebody's afternoon chasing a phantom.

### Nothing is ever assumed compliant

[`app/assessments/engine.py`](app/assessments/engine.py) evaluates one
control against one target in a fixed order, and the order is the whole
design:

1. **`NOT_APPLICABLE` short-circuits everything.** A control an
   organization has formally scoped out is not a requirement — it must
   leave the denominator entirely, not sit in it as a hidden pass.
2. **Not automatable → `NOT_ASSESSED`, never `PASS`.** A control that
   needs a human to read a policy document cannot be satisfied by a
   scanner that found nothing to complain about.
3. **No evidence → `NOT_ASSESSED`, never `PASS`.** The single most
   important line in the module: a collector that silently returned
   nothing must not certify the host it failed to reach. Defaulting to
   pass here is how compliance tools come to report green estates they
   never inspected.
4. Only *then* is the rule evaluated — and only a *failure* consults the
   waivers, because waiving a pass is meaningless and waiving an error
   would hide a broken collector behind a business decision.

### Scoring is weighted, and says what it excluded

[`app/scoring/engine.py`](app/scoring/engine.py) weights every control
by [`SEVERITY_WEIGHTS`](app/models/enums.py) — informational controls
carry **zero** weight, so a hundred passing informational controls can
never drown out one failing critical one. Nine passing low-severity
controls and one failing critical is 90% by raw count and under 50%
weighted; the weighted number is the one this service reports.

**An excepted control counts as satisfied**, not failed — an exception
is a documented, approved, expiring acceptance of a specific risk, and
scoring it as a failure would mean an organization that governs its
exceptions properly scores worse than one that never files any. What
stops this from becoming a loophole: exceptions are counted and reported
separately, so "our score is 94%, and 40% of that is waivers" stays a
sayable sentence.

**Coverage is computed alongside every score.** A 100% score across 4%
coverage is not compliance, and printing the two together is what stops
the first number from being read as though it were both.

### Evidence is immutable by construction

Every row is content-hashed at creation over a canonically-ordered
rendering of its payload
([`content_digest`](app/models/evidence.py)), so the digest is
reproducible across machines and Python versions. The repository never
updates a payload; correction is by **supersession** — a new row points
at the old one and both survive. An auditor who finds one editable row
in a trail has to discard the whole trail; a digest that can be
recomputed and compared is what lets them trust the rest of it.

### Findings are deduplicated by fingerprint, not by luck

[`app/risk/engine.py`](app/risk/engine.py)'s `fingerprint()` deliberately
excludes the assessment id, the timestamp, and the observed values. A
thousand-host daily assessment must update one finding per problem, not
raise a new one every run — and a host whose patch level moves from 4.1
to 4.2 while still being out of date is the *same* unresolved problem,
so including the observed value would reset an age somebody is being
measured against. A closed finding that recurs **reopens** rather than
duplicating, with its resolution fields cleared, because a resolution
that did not hold must not survive the reopening.

### Remediation verification re-checks the control, not the checkbox

`RemediationService.verify` reads the **latest actual result** for the
finding's control before it will mark a task `VERIFIED` or close the
finding. "We ran the playbook" and "the control now passes" are
different claims, and only the second one may close a finding — an
automated remediation that silently failed would otherwise close the
finding it did not fix, and the failure would stay invisible until the
next audit found it independently.

---

## Layout

| Path | What lives there |
| --- | --- |
| [`app/rules/`](app/rules/) | 29 pure comparison operators over a dispatch table — nothing from a stored control is ever executed |
| [`app/assessments/`](app/assessments/) | The pure evaluation engine: guard order, waivers, ceilings |
| [`app/scoring/`](app/scoring/) | Weighted scoring, coverage, trend |
| [`app/risk/`](app/risk/) | Risk scoring (derived, never entered), fingerprinting, due dates |
| [`app/frameworks/builtin.py`](app/frameworks/builtin.py) | CIS, NIST 800-53, ISO 27001, IEC 62443, SOC 2 — every shipped control is automatable and tested to actually fail |
| [`app/models/`](app/models/) | 16 tables |
| [`app/repositories/`](app/repositories/) | 16 repositories, `require_in_org` named apart from the base's unscoped `require_by_id` |
| [`app/services/`](app/services/) | 11 services — the only layer touching infrastructure |
| [`app/api/`](app/api/) | 61 paths, 73 operations |
| [`app/workers/`](app/workers/) | Scoring rollup, exception-expiry + stuck-assessment sweep — both leader-elected |

---

## Running it

```bash
docker build -t aiios/compliance-service:0.1.0 \
  -f services/compliance-service/Dockerfile .

docker run -d --name aiios_compliance \
  --network aiios_aiios_network -p 8022:8022 \
  -e AIIOS_DATABASE_HOST=aiios_postgres -e AIIOS_DATABASE_PORT=5432 \
  -e AIIOS_DATABASE_NAME=aiios_compliance \
  -e AIIOS_DATABASE_USER=aiios -e AIIOS_DATABASE_PASSWORD=change-me \
  -e AIIOS_REDIS_HOST=aiios_redis -e AIIOS_REDIS_DB=24 \
  -e AIIOS_REDIS_PASSWORD=change-me \
  -e AIIOS_RABBITMQ_HOST=aiios_rabbitmq -e AIIOS_RABBITMQ_USER=aiios \
  -e AIIOS_RABBITMQ_PASSWORD=change-me -e AIIOS_RABBITMQ_VHOST=/aiios \
  -e AIIOS_APPLICATION_PORT=8022 \
  aiios/compliance-service:0.1.0
```

`GET /readiness` reports both PostgreSQL and Redis. Migrations:
`uv run alembic upgrade head`. `keys/jwt_public_key.pem` is the public
half of `services/authentication-service`'s signing key — this service
verifies but never issues tokens.

---

## Tests

393 tests, **95.17%** branch coverage, against real PostgreSQL, Redis,
and RabbitMQ — including job registration against a real
`SchedulerManager`, because the thing worth proving is that this
service's job definitions are ones the framework actually accepts.

```bash
uv run python -m pytest -q --cov=app --cov-branch --cov-fail-under=95
```

### Two response-envelope classes exist in this codebase

`shared_core.responses.success.SuccessResponse` has no `meta` field.
`app.schemas.response.SuccessResponse` does, and carries the request id
that ties a response back to its log lines. Importing the wrong one
type-checks cleanly and fails every single endpoint at response
validation — caught immediately by the first API test written, not
shipped, but worth naming as the reason every route imports
`from app.schemas.response import ResponseMeta, SuccessResponse`
explicitly rather than the shared-core path.

### The one thing the HTTP tests cannot tell you

The `app` fixture overrides only the request session, so a test's writes
roll back — which changes **transaction lifetime**, and anything
depending on transaction lifetime is untestable there. `AuditService
.record_failure` commits in its own `session_scope` so a refused
request's audit entry survives the rollback of the request that raised;
under the SAVEPOINT that distinction vanishes and the test would pass
either way. Tested at service level against the real session factory
instead, the same way Prompt 050 tests the analogous case.

---

## Notes worth keeping

- **A normaliser's own docstring did not stop it being misused.**
  `assessment_status_of(stored)`, `framework_status_of(stored)`,
  `exception_status_of(stored)`, `finding_status_of(stored)`,
  `risk_status_of(stored)`, and `remediation_status_of(stored)` were all
  called on the ORM *record* instead of its `.status` column, across
  four services. Every one of the ten call sites would have raised
  `ValueError` on first use — archiving a framework, cancelling an
  assessment, approving an exception, closing a risk, verifying a
  remediation. Caught by the service tests, not by review. The lesson
  carried over from Prompt 050's `require_by_id`/`require_in_org`
  confusion: a correct-looking call that silently takes the wrong
  argument shape is not something a docstring fixes.

- **`exceptions.finding_id` was dropped from the schema before it ever
  shipped.** One exception waives *many* findings — the same
  unpatched control across forty hosts is forty findings and one
  waiver — so the relationship belongs on the many side, as
  `ComplianceFinding.exception_id`. A column on the exception could only
  name one of the findings it waives and would disagree with the rest;
  it also closed a foreign-key cycle no `CREATE TABLE` ordering could
  satisfy, which is how the redundancy announced itself during the
  first migration attempt.

- **A shipped catalogue is only worth as much as its automation.** Every
  control in `app/frameworks/builtin.py` is tested to actually *fail*
  against an unrelated evidence payload — not just to compile — because
  a control that passes unconditionally certifies an estate nobody
  looked at, and a shipped catalogue full of those would look
  impressive while assessing nothing.

- **Derived, never entered**, carried forward as a pattern from
  Prompt 050's `EFFECT_PRECEDENCE`: risk severity is `severity_for
  (likelihood, impact)`, never a field somebody fills in — a register
  where a risk's owner can type "low" beside `almost_certain`/`severe`
  hides exactly the risks it exists to surface, and the owner is the
  person most motivated to type it.
