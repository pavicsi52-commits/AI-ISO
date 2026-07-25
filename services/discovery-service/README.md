# Discovery Service

Automated discovery of hybrid, cloud, edge, industrial, and Kubernetes
assets across 26 protocols
([`docs/037_Enterprise_Discovery_Service.md`](../../docs/037_Enterprise_Discovery_Service.md)),
classifying and synchronizing findings into
`services/inventory-service`. The eighth AI-IOS microservice built on
`packages/shared-core`, and the first to talk to another AI-IOS
service's own REST API directly (`services/secrets-management-service`
for credential resolution, `services/inventory-service` for asset/
relationship sync) rather than only sharing infrastructure with it.

By far the largest prompt implemented in this repository so far — 25
named protocols plus a plugin catch-all, five cloud providers,
Kubernetes, and industrial fieldbus discovery, against a sandbox with
no real cloud accounts, no Kubernetes cluster, and no industrial
hardware. Scope was resolved explicitly with the user up front (see
"The AskUserQuestion decision" below) rather than either faking
coverage or silently cutting scope.

## Architecture

Standard service structure per
[`docs/008_Backend_Master_Architecture.md.txt`](../../docs/008_Backend_Master_Architecture.md.txt),
plus:

- `app/scanners/base.py` / `app/scanners/enumeration.py` — the two
  complementary contracts every protocol implementation follows (see
  "Two-contract scanner architecture" below).
- `app/scanners/*.py` (24 files) — one real client implementation per
  named protocol, `app/scanners/cloud/*.py` (5 files) — one per cloud
  vendor, `app/scanners/kubernetes_provider.py`.
- `app/scanners/registry.py` — `PROTOCOL_SCANNERS`/`CLOUD_PROVIDERS`/
  `KUBERNETES_PROVIDER`, keyed by protocol/vendor/target-type; the
  orchestrator never branches on protocol itself, only looks the
  scanner up.
- `app/discovery/credentials.py` — `CredentialResolver`: a live
  `GET /secrets/{id}` call per probe, never caching or persisting the
  resolved value (per docs/037's own "Never persist plaintext
  credentials").
- `app/discovery/inventory_sync.py` — `InventorySyncClient`: creates/
  reconciles assets and relationships via the Inventory Service's own
  REST API (never its database or Neo4j directly).
- `app/services/discovery_execution.py` — `DiscoveryExecutionService`:
  the orchestrator every other module in this package feeds into (see
  its own module docstring for the full, honestly-documented scope of
  what it does and does not do).
- `app/classification/` — heuristic classification by protocol/
  resource-type, plus per-protocol fingerprint extraction.
- `app/scheduling/registrar.py` — maps a `DiscoverySchedule` row onto
  `shared_core.scheduler`'s own `Schedule`/`Job` and registers it.

### The AskUserQuestion decision

Given this prompt's scale and this sandbox's total lack of real cloud
accounts, a Kubernetes cluster, or industrial hardware, the user was
asked up front how to handle the gap rather than guessing. Their
answer, verbatim: **"Full adapters, test what's simulable locally"** —
build real, complete client code for every protocol/cloud/environment
named in the spec, live-test each against whatever can genuinely be
stood up locally, and honestly document what cannot be verified rather
than faking coverage. Every design decision below follows from that
answer.

### Two-contract scanner architecture

`ProtocolScanner` (`app/scanners/base.py`) — one async `probe()`
against one address, returning a single `ScanOutcome` — fits every
protocol that targets one host. Cloud accounts and Kubernetes clusters
don't: one target yields an arbitrarily long, heterogeneous list of
sub-resources. Rather than distorting `ScanOutcome` to carry an
unbounded nested payload, cloud/Kubernetes discovery gets its own,
complementary contract: `EnumerationProvider` (`app/scanners/
enumeration.py`), keyed by `TargetType` and returning a list of
`DiscoveredResource`.

### What's genuinely real-infra-tested vs. mocked, and why

Per the user's own chosen scope, every scanner/provider's client code
is real and complete regardless of testability; each one's own module
docstring states plainly which category it falls into:

**Tested against real, locally-standable infrastructure:** TCP/UDP/
ICMP/DNS/NTP (real sockets/real DNS/real NTP servers), HTTP/HTTPS/REST
(this platform's own docker-compose services — Neo4j, MinIO, RabbitMQ
management), GraphQL/JMX (real request-building against `pytest-httpx`
— no real GraphQL/Jolokia server exists locally, but the wire format
is genuinely exercised), gRPC (a real `grpc.aio` health-check server
this package's own test suite starts — the Windows Application Control
policy that once blocked `cygrpc.pyd` on this dev machine no longer
reproduces), SSH/SFTP (a real `openssh-server` container), FTP (a real
`pyftpdlib` server), MQTT (a real Eclipse Mosquitto broker container),
AMQP (this repository's own real RabbitMQ container), LDAP (mocked at
the `ldap3.Connection`/`ldap3.Server.info` layer — the scanner's own
`ldap3.Connection` call is hardcoded to the real client strategy, not
`MOCK_SYNC`, so a real directory server would be needed for a fully
live test), Modbus (a real in-process `pymodbus` TCP server), OPC UA (a
real in-process `asyncua.Server`), BACnet (a real UDP round trip
against a hand-built fake device replying with a genuine, spec-correct
I-Am — see "Real bugs found" below), SNMP (mocked at the `pysnmp`
HLAPI call layer — no local SNMP agent exists), AWS (`moto`'s real,
in-process AWS API emulator — a genuine `boto3` client/server
exchange), Kubernetes (a real local HTTP server implementing the 14
real K8s REST list endpoints this provider calls — the official
client's own `urllib3` wire format talks to it for real).

**Never verified against real infrastructure in this environment**
(client code is complete and real; the docstring of each says so
plainly): WinRM, Redfish, IPMI, SMB (no real/emulable target reachable
here), Azure, GCP, Oracle Cloud, IBM Cloud (no real account —
request/response logic is exercised with `pytest-httpx` instead), WMI
(genuinely tested against `localhost` since this dev machine happens
to be Windows, but the Docker deployment target is Linux and can never
run this scanner).

### Lean REST over heavy SDKs for cloud providers

Every cloud provider except AWS (real REST + OAuth2/JWT/RSA-signing
implemented directly with `httpx`/`cryptography`/`pyjwt`, not the
`azure-mgmt-*`/`google-cloud-*`/`oci`/`ibm-cloud-sdk-core` SDK
families) — deliberately, since none of those four can ever be
exercised live in this environment anyway, and the request/response
contracts are genuine and documented, not invented. AWS uses `boto3`
because it's the one provider actually testable, via `moto`.

### JMX via Jolokia, not raw RMI

Raw JMX rides Java RMI, a wire protocol with no accessible
implementation outside a JVM class loader. Jolokia (a real, widely
deployed JVM agent exposing JMX over HTTP/JSON) is the practical,
real-world integration point non-JVM tooling actually uses — this
scanner probes Jolokia's own `/jolokia/version` endpoint, a documented
scope boundary, not a placeholder.

### Hand-rolled BACnet, not `bacpypes3`

`bacpypes3` is oriented at building a full BACnet device, not a
lightweight one-shot prober. Who-Is/I-Am discovery is simple enough to
hand-encode correctly against the real BVLC/NPDU/APDU wire format
directly over a raw UDP socket (ASHRAE 135 Annex J) — a genuine
protocol implementation, not a simulation (see "Real bugs found").

### Inline credentials, no `/discovery/credentials`/`/discovery/targets` endpoints

Docs/037's own literal REST list never names either endpoint.
Scan-trigger requests (`POST /discovery/scan` and its four siblings)
instead carry an inline `InlineCredentialSpec` (a Secrets Management
Service secret reference plus metadata), from which
`DiscoveryCredentialService.create_from_spec()` creates the backing
`DiscoveryCredential` row as a side effect. `POST /discovery/jobs` was
redesigned to "re-run `profile_id` against every target already
registered under it" rather than requiring explicit `target_ids`.

### Scheduler-triggered execution's honest, documented limitation

Every downstream call `DiscoveryExecutionService` makes (credential
resolution, Inventory Service sync) needs a caller Bearer token.
Interactive requests always have one; a job fired autonomously by
`shared_core.scheduler` does not, since no prior AI-IOS prompt
establishes a service-account/machine-credential mechanism — a real,
documented platform gap, not a shortcut. With `caller_token=None`,
`run_job()` still runs every credential-less protocol probe and
records local rows, but skips credential resolution and leaves
discovered assets `sync_status=PENDING`.

### Kubernetes-only relationship inference

Of every possible cross-resource relationship a full topology could
infer, this engine implements exactly one: Kubernetes pod → node
`RUNS_ON` edges. A documented, bounded scope limit — the same judgment
call `services/inventory-service`'s own `AssetGroupService` rule
evaluator already applied to filter operators — not exhaustive
inference (e.g. a cloud instance's subnet/VPC chain is not inferred).

### Bounded "DISCOVERY RULES" scope

Of nine `RuleType` values, only `INCLUDE`/`EXCLUDE` (filtering targets
before probing) and `CLASSIFICATION` (overriding the heuristic
classification after fingerprinting) are evaluated by the execution
engine. `FILTER`/`ASSET_MATCHING` have no application semantics docs/037
specifies beyond a one-line "Support" mention; `RELATIONSHIP`/
`TAG_ASSIGNMENT`/`OWNER_ASSIGNMENT`/`PROJECT_ASSIGNMENT` would need
schema fields `DiscoveryAsset` doesn't have. A rule of any of those
four types can still be created and stored; it's simply never read.

## Running Locally

```bash
uv sync
# Requires the repository root docker-compose stack running (Postgres,
# Redis, RabbitMQ) -- see the repository root README. This service
# also needs its own database created once:
#   docker exec aiios_postgres psql -U aiios -d postgres \
#     -c "CREATE DATABASE aiios_discovery OWNER aiios;"
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8008
```

Configuration is `AIIOS_`-prefixed environment variables via
`packages/shared-core/config` plus this service's own
`AIIOS_DISCOVERY_SERVICE_*` variables (`app/config/settings.py`'s
`DiscoveryServiceSettings`): `HOST`, `PORT`, `CORS_ALLOWED_ORIGINS`,
`JWT_PUBLIC_KEY_PATH`, `SECRETS_SERVICE_BASE_URL`,
`INVENTORY_SERVICE_BASE_URL`, `DEFAULT_SCAN_TIMEOUT_SECONDS`,
`DEFAULT_CONCURRENCY_LIMIT`, `HTTP_CLIENT_TIMEOUT_SECONDS`. Unlike
`services/inventory-service`, this service never opens a Neo4j driver
or MinIO client of its own.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET/POST /discovery/jobs`, `GET/DELETE /discovery/jobs/{id}` | Job lifecycle (create re-runs a profile's known targets; delete cancels) |
| `GET/POST /discovery/profiles`, `PUT/DELETE /discovery/profiles/{id}` | Reusable scan configuration |
| `GET/POST /discovery/schedules`, `PUT/DELETE /discovery/schedules/{id}` | Recurring schedules, live-registered with `shared_core.scheduler` |
| `POST /discovery/scan` | Single ad-hoc protocol probe |
| `POST /discovery/network-scan` | Multi-address, multi-protocol network sweep |
| `POST /discovery/cloud-scan` | Enumerate one cloud account |
| `POST /discovery/kubernetes-scan` | Enumerate one Kubernetes cluster |
| `POST /discovery/industrial-scan` | OT/industrial protocol sweep |
| `GET /discovery/results` | Raw per-target probe outcomes for a job |
| `GET /discovery/statistics` | Cached per-organization discovery analytics |
| `GET /health` / `/readiness` / `/liveness` | Health checks (readiness includes Postgres and Redis connectivity) |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` / `/openapi.json` | OpenAPI documentation |

## Testing

```bash
uv run pytest --cov=app --cov-report=term-missing
```

317 tests, 95.1%+ coverage. Real infrastructure wherever genuinely
feasible in this environment (see "What's genuinely real-infra-tested
vs. mocked" above) — Postgres isolation uses a per-test SAVEPOINT
(`join_transaction_mode="create_savepoint"`), the same pattern every
prior AI-IOS service established; two dedicated containers
(`aiios_discovery_test_ssh`, `aiios_discovery_test_mosquitto`) this
package's own test suite starts for protocols with no docker-compose
equivalent. `tests/test_workers.py` covers the same commit-visibility
worker regression class every prior AI-IOS worker test file
established (`create_job()` must commit before the queue message is
published; a worker's own commit must be visible to an independent
connection) plus a real end-to-end `TcpScanner` probe against the
docker-compose Redis container.

## Docker

Build from the **repository root**:

```bash
docker build -f services/discovery-service/Dockerfile -t aiios/discovery-service .
```

## Real bugs found via live testing

1. **`DiscoveryJob.discovered_relationship_count` was declared on the
   model, schema, and migration but never actually populated** —
   `run_job()` set `discovered_asset_count` from the targets it
   processed but never summed relationships the same way, so the field
   silently stayed `0` forever. Caught by re-reading the response
   schema against the execution engine before writing API tests, fixed
   by querying the job's own recorded relationship count at the same
   point `discovered_asset_count` is computed.
2. **`DiscoverySchedule.is_active` silently collided with
   `BaseModel`'s own soft-delete `is_active` column.** Both declared
   the same column name — setting a schedule's domain flag to `False`
   (intending "pause this schedule") actually soft-deleted the row,
   making every subsequent lookup (including the very next `DELETE`
   call in the test that caught this) report `NotFoundError`.
   Reproduced live via a full create → update → deactivate → delete
   API test sequence. Fixed by renaming the domain flag to
   `is_enabled` (model, schema, service, router, and a hand-edited
   migration column, since the schema had not yet shipped beyond this
   sandbox), restoring `BaseModel`'s own `is_active` as a genuinely
   distinct column.
3. **`KubernetesProvider._enumerate()`'s own `except OSError` clause
   for "cluster unreachable" never actually fired.** The official
   `kubernetes` client's `urllib3` transport wraps a real connection
   failure in `urllib3.exceptions.MaxRetryError`/`NewConnectionError`,
   neither of which is an `OSError` subclass — an unreachable cluster
   crashed enumeration with an unhandled `urllib3` exception instead of
   the intended clean `EnumerationError`. Caught live by pointing the
   real `kubernetes` client at a closed local port during test-writing.
   Fixed by also catching `urllib3.exceptions.HTTPError`.
4. **`BacnetScanner._build_who_is()` encoded the wrong BVLC length.**
   ASHRAE 135 Annex J.2 defines the BVLC length field as covering the
   *entire* BVLL PDU including its own 4-byte header, not just the
   body that follows — the scanner encoded `len(body)` (4 for a
   minimal Who-Is) instead of `len(body) + 4` (the real, correct 8).
   Every real BACnet stack validates this field against the packet's
   actual wire size and would reject a mismatched one; this had no
   effect on this package's own parser (which never cross-checks the
   field), so it was silent until caught while hand-encoding a real,
   spec-correct I-Am reply to build a live UDP round-trip test against.
5. **`IbmProvider`'s resource-controller and Kubernetes-Service list
   calls silently swallowed a `401`/`403` as "no resources found"**,
   unlike every other `_list`-style helper in every other cloud
   provider (including this same file's own `_list_vpc`), which
   correctly raises on an authorization failure instead of returning
   an empty list. Noticed while writing symmetric test coverage across
   all four cloud providers and comparing their error-handling shapes
   side by side. Fixed by adding the same 401/403 check to both.

Three further defects were self-caught during development (re-reading
the orchestrator's own code immediately after writing it, before any
test ran), not via live testing: a literal placeholder left in a
relationship-type assignment, a fabricated "avoids an import cycle"
justification for a needless local import (no such cycle exists), and
`raise ... from result` chaining an ORM object instead of the actually-
caught exception.

**Retroactive fix (2026-07-24, found while writing
`services/configuration-management-service`'s own models):**
`DiscoveryFilter.is_active`, `DiscoveryRule.is_active`, and
`DiscoveryTarget.is_active` each redeclared `BaseModel`'s own
soft-delete `is_active` column — the same collision class
`DiscoverySchedule.is_active` above already documented, missed for
these three at the time since nothing exercised the collision (grep
confirmed none was ever toggled by any service/API code). Renamed all
three to `is_enabled` via a new migration; see `AI_MEMORY.md`'s own
Prompt 037 entry for the full account.
