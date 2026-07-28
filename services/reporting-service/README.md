# Reporting Service

The AI-IOS enterprise reporting engine (Prompt 047). Designs, renders,
schedules, exports, distributes, and archives reports drawn from every
platform service.

- **Port** `8018` · **Database** `aiios_reporting` · **Redis db** `20`
- **Routes** 35 · **Tests** 344 · **Coverage** 95.92%

## What it does

| Capability | Where |
|---|---|
| Report designer (sections, charts, branding, themes) | `app/reports/designer/` |
| Rendering engine (bounded-concurrent source fetches) | `app/renderer/` |
| Export in 7 formats | `app/export/` |
| Scheduling with time zones, retry, failure notices | `app/scheduler/`, `app/workers/` |
| Distribution over 6 channels | `app/distribution/` |
| Immutable archive with retention and integrity checks | `app/archive/` |
| AI narrative sections via Prompt 046 | `app/ai/` |
| Filtering, parameters, analytics, audit | `app/filters/`, `app/parameters/`, `app/services/` |

## Design decisions worth knowing

**Every data source is read with the caller's own bearer token.** This
service never holds a privileged credential, so a report cannot contain
data the requesting user could not have fetched themselves. A 403 from
a source is the correct outcome, not a bug. Scheduled runs are the one
exception and use an explicitly configured service identity — a visible
seam, not a silent escalation (see `SCHEDULED_RUN_TOKEN`).

**A failing section degrades; it does not abort the report.** One
unreachable source marks its own section unavailable and the rest still
renders, with the gap recorded on the section and surfaced as
`degraded_sections` in the API. An infrastructure report delivered with
an honest gap is far more useful than nothing.

**Filters are applied here, over already-fetched rows.** The twelve data
sources do not share a filter grammar, so one expression could not be
translated to all of them faithfully. Applying one consistent grammar
in this service means "status equals firing" means the same thing
whichever source the rows came from. Source-side filters should still
be used where they exist — that is what a section's `query.params` is
for.

**Concurrency is network-only and bounded.** Section fetches overlap
under a semaphore because they are HTTP. Nothing touches the database
concurrently: an `AsyncSession` is not safe for concurrent use even for
reads, the rule every AI-IOS service has followed since
`services/validation-service`.

**Templates are versioned and approved before use.** A template is
executable content that queries production systems; running an
unreviewed one is exactly what the gate prevents. Generation resolves
through `resolve_for_execution`, never "the newest row".

**The archive keeps its own bytes and checksum.** Regenerating or
deleting a report cannot retroactively change what was archived, and
`download` verifies the checksum before serving — so tampering or
storage corruption is detected rather than handed to an auditor.
Purging inside the retention window is refused, and a purge keeps the
row (dropping only the bytes) so the evidence that the artifact existed
survives.

**Shared-link tokens are returned exactly once.** The token is a bearer
credential for an otherwise unauthenticated recipient, so it is
returned only to the caller who created it and never appears in any
listing endpoint. Expiry is enforced on every redemption.

### Never shadow a base column

`shared_core.base.BaseEntityMixin` owns `id`, `created_at`,
`updated_at`, `deleted_at`, `created_by`, `updated_by`, `deleted_by`,
**`version`**, `is_active`, `organization_id`, and `project_id`.

`version` is used for **optimistic locking**, and
`BaseRepository.update()` increments it on every write. A model that
redeclares `version` for its own meaning gets that meaning silently
corrupted by unrelated updates *and* loses optimistic locking.

This shipped here as a live bug: archive generations jumped from 1 to 4
across two updates. The column is now `archive_version`, and
`tests/test_services.py::TestBaseColumnShadowing` guards both the
behaviour and the general rule so the next model cannot reintroduce it.
The same collision was found (latent) in
`services/secrets-management-service`'s encryption keys, where it would
have corrupted key-rotation ordering.

## Honest limits

- **PDF "digital signature" is not a PKI signature.** `reportlab`
  cannot produce PKCS#7, and no signing library is in this platform's
  dependency set. What is implemented is a visible signature block with
  the signer, timestamp, and a SHA-256 digest of the report content —
  enough to detect alteration, but not a certificate-backed signature.
  Real signing means taking a dependency such as `pyhanko`. **Password
  protection is genuine** AES encryption via `reportlab`'s own
  `StandardEncryption`.
- **PDF tables truncate at 2,000 rows**, visibly, with a line stating
  how many were omitted and pointing at CSV/XLSX. `reportlab` lays out
  every row in memory; the alternative is an out-of-memory event for
  the whole process.
- **Email delivery does not attach the artifact.** `shared_core`'s
  notification manager sends a body, not attachments. The recipient is
  told the report is ready and fetches it through an authenticated
  download — which also avoids mailing infrastructure data unencrypted.
- **Chart rendering is deliberately plain.** PDF charts are
  proportional bars built from table cells and HTML charts are inline
  CSS bars, so both render with no network access and in any email
  client. No charting library is involved.
- **`MONTHLY` recurrence approximates nothing** — it clamps to the
  month's last valid day (Jan 31 → Feb 28), which is verified by test.

## Running it

```bash
uv run alembic upgrade head
uv run uvicorn main:app --host 0.0.0.0 --port 8018
```

```bash
docker build -f services/reporting-service/Dockerfile -t aiios/reporting-service .
```

The build context **must** be the repository root — this service is a
member of the root `uv` workspace and depends on `packages/shared-core`
as a path dependency. Migrations run as a separate step, never in
`CMD`, so a multi-replica rollout cannot race two containers running
the same migration.

## Configuration

All variables use the `AIIOS_REPORTING_SERVICE_` prefix (shared
infrastructure uses plain `AIIOS_`).

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `8018` | |
| `JWT_PUBLIC_KEY_PATH` | `keys/jwt_public_key.pem` | Verification key only |
| `MAX_ROWS_PER_REPORT` | `50000` | Hard ceiling; a report above it fails with a clear message rather than exhausting memory |
| `MAX_PARALLEL_SECTIONS` | `4` | Bounds concurrent *source fetches* only |
| `ARCHIVE_RETENTION_DAYS` | `365` | Stored per archived row, so a policy change never shortens existing retention |
| `SHARE_LINK_TTL_SECONDS` | `604800` | |
| `OBJECT_STORAGE_BUCKET` | `aiios-reports` | Object storage is optional; without MinIO credentials that one channel reports unavailable and the service still starts |
| `WEBHOOK_TIMEOUT_SECONDS` | `15` | |
| `SCHEDULER_ENABLED` | `true` | Leader-elected via `shared_core.scheduler`, so replicas cannot duplicate a run |
| `SCHEDULER_POLL_SECONDS` | `60` | |
| `SCHEDULED_RUN_TOKEN` | *(empty)* | Service identity for unattended runs; sources still enforce RBAC against it |
| `AI_REPORTING_ENABLED` | `true` | AI sections degrade cleanly when disabled |
| `<SERVICE>_BASE_URL` | localhost defaults | One per data source |

## Testing

```bash
uv run python -m pytest --cov=app --cov-report=term-missing
```

Tests run against the repository's real Postgres, Redis, and RabbitMQ
with per-test `SAVEPOINT` isolation. Export tests assert on genuine
artifacts: the PDF starts with `%PDF`, the XLSX is a real zip that
`openpyxl` reopens, the JSON and XML parse, and escaping is verified
against content containing `</td>`, quotes, and pipes.

**Data sources are the one thing stubbed**, behind an
`httpx.MockTransport` serving the platform's own envelope — a report
suite cannot stand up twelve other services, and everything that
actually belongs to this service runs for real.

**Test hosts must be `127.0.0.1`, never `localhost`.** On Windows
`localhost` resolves to `::1` first and Docker Desktop's IPv6
forwarding hangs rather than refusing. Diagnosed during Prompt 045.

**Prefix `docker run` with `MSYS_NO_PATHCONV=1`** when any argument
starts with `/` — Git Bash rewrites `/aiios` into a Windows path and
the container dies on an opaque AMQP error.
