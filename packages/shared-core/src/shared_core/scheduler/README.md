# Enterprise Scheduler Framework

A centralized scheduler for AI-IOS
(docs/026_Enterprise_Scheduler_Framework.md.txt "OBJECTIVE"): One-Time,
Cron, Recurring, Delayed, Workflow-Timer, Maintenance, and every other
documented job type, with retry, dependencies, distributed scheduling,
cluster coordination, and high availability. Built almost entirely on
primitives this monorepo already has -- cron computation on
`shared_core.queue.scheduler`, distributed locking/leader election on
`shared_core.cache.locks`, retry/backoff on `shared_core.queue.retry`,
durable delivery on `shared_core.queue`, health status on
`shared_core.monitoring`, and metrics on `shared_core.metrics`.

## Developer Guide

```python
from shared_core.scheduler import (
    Schedule, ScheduleType, JobType, build_job, create_scheduler_framework,
)

manager = create_scheduler_framework(queue_manager, redis_client)

async def send_report(job) -> None:
    ...  # business logic lives outside this framework

job = build_job(
    job_name="nightly-report",
    job_type=JobType.REPORT,
    fn=send_report,
    schedule=Schedule(schedule_type=ScheduleType.CRON_EXPRESSION, cron_expression="0 2 * * *"),
)
manager.register_job(job)

await manager.start()   # heartbeat, leader election, failover, dispatch loop, worker
...
await manager.stop()    # graceful shutdown, reverse order
```

`create_scheduler_framework()` is the one call a service's startup
makes: it wires the registry, engine, queue, executor, and every
distributed-coordination piece into one running `SchedulerManager`. It
takes already-connected `QueueManager`/`Redis` clients rather than
building its own connections, since a service almost always shares one
connection pool across every framework that needs Redis/RabbitMQ.

### Declaring jobs with decorators

```python
from shared_core.scheduler.decorators import build_job_from_decorated, cron, retryable, timeout

@cron("*/15 * * * *")
@retryable(max_attempts=5, backoff_base_seconds=2.0)
@timeout(30.0)
async def sync_inventory(job) -> None:
    ...

job = build_job_from_decorated(sync_inventory, job_name="sync-inventory", job_type=JobType.AUTOMATION)
manager.register_job(job)
```

`@cron` is reachable at `shared_core.scheduler.decorators.cron`, not
the package root -- see "Architecture Notes".

### Scheduling types

```python
Schedule(schedule_type=ScheduleType.IMMEDIATE)
Schedule(schedule_type=ScheduleType.SCHEDULED_TIME, run_at=some_datetime)
Schedule(schedule_type=ScheduleType.CRON_EXPRESSION, cron_expression="0 2 * * *")
Schedule(schedule_type=ScheduleType.FIXED_DELAY, delay=timedelta(minutes=5))
Schedule(schedule_type=ScheduleType.FIXED_RATE, interval=timedelta(minutes=30))
Schedule(schedule_type=ScheduleType.CALENDAR_SCHEDULE, calendar_rule="MON-FRI 09:00-17:00")
Schedule(schedule_type=ScheduleType.BUSINESS_HOURS, calendar_rule="MON-FRI 09:00-17:00")
Schedule(schedule_type=ScheduleType.EVENT_TRIGGERED, event_name="order.created")
```

`shared_core.scheduler.engine.compute_next_run()` turns any of these
into the job's next UTC due time; `SchedulerEngine.due_jobs()` returns
every registered job that's both due and dependency-satisfied.

### Dependencies

```python
from shared_core.scheduler.dependency import DependencyGraph, JobDependency

dependencies = DependencyGraph()
dependencies.add(JobDependency(job_id=child.job_id, depends_on_job_id=parent.job_id))
dependencies.has_cycle()  # detect a bad dependency graph before it deadlocks scheduling
```

Pass the same `DependencyGraph` into `SchedulerEngine(registry, dependencies)`
-- a job with an unsatisfied dependency is never reported due, however
stale its `next_run`.

### Distributed scheduling

```python
from shared_core.scheduler import LeaderElection, HeartbeatSender, HeartbeatRegistry, FailoverCoordinator

leader = LeaderElection(redis_client, node_id)
await leader.campaign()          # single attempt
await leader.start()             # background campaign loop

heartbeat = HeartbeatSender(HeartbeatRegistry(redis_client), node_id)
await heartbeat.start()

async def on_node_failed(failed_node_id: str) -> None:
    ...  # reassign that node's in-flight jobs

failover = FailoverCoordinator(HeartbeatRegistry(redis_client), on_node_failed)
await failover.start()
```

Only the elected leader dispatches due jobs
(`SchedulerManager.dispatch_due_jobs()`); every node (leader or not)
runs jobs pulled off the durable `JobQueue` -- "Split-Brain Prevention".
A job's own "Exclusive Execution" lock
(`shared_core.scheduler.locking.exclusive_job_execution`) is separate
from leadership: it prevents two workers from running the *same job*
concurrently, regardless of which node is leader.

### Middleware

```python
from shared_core.scheduler.middleware import (
    apply_middleware, execution_logging_middleware, correlation_id_middleware,
    error_handling_middleware, metrics_collection_middleware, build_audit_middleware,
)

handler = apply_middleware(executor.execute, [
    execution_logging_middleware, correlation_id_middleware,
    build_audit_middleware(node_id), error_handling_middleware, metrics_collection_middleware,
])
worker = Worker(node_id, registry, engine, queue, executor, handler=handler)
```

`create_scheduler_framework()` applies exactly this chain by default;
pass `middlewares=[...]` to replace it, or `middlewares=[]` to run with
none. Security/tenant validation and telemetry tracing are available in
`shared_core.scheduler.middleware` but not included by default -- they
need a caller-supplied permission callback or a configured `Tracer`,
neither of which this framework can assume (docs/026 "DO NOT
IMPLEMENT": Authentication).

### Health and metrics

```python
from shared_core.scheduler.health import build_health_report
from shared_core.scheduler import metrics as scheduler_metrics

report = await build_health_report(registry, heartbeat_registry, redis_client, rabbitmq_connection)
report.status  # HealthStatus: worst-case of worker/leader/queue/heartbeat status

scheduler_metrics.scheduler_registered_jobs
scheduler_metrics.scheduler_job_duration_seconds  # Prometheus histogram
```

## Architecture Notes

- **`JobStatus` extended additively, not repurposed**: the Prompt 021
  baseline (`PENDING`/`QUEUED`/`RUNNING`/`COMPLETED`/`FAILED`/
  `CANCELLED`/`TIMED_OUT`) remained semantically correct for this
  framework's needs -- just incomplete against docs/026's full "JOB
  LIFECYCLE" (`Registered`/`Scheduled`/`Retrying`/`Paused`/`Expired`/
  `Archived`). Six values were added; none of the original seven
  changed meaning. Matches the same additive-extension precedent as
  `HealthStatus` (Prompt 023).
- **`@cron`/`cron.py` naming collision, resolved the same way as
  Prompt 024's `trace`/`span`**: `shared_core.scheduler.decorators.cron`
  (the job-declaration decorator) and `shared_core.scheduler.cron` (the
  cron-computation submodule) share a bare name. Python auto-binds
  submodules as package attributes on import, so the submodule wins at
  `shared_core.scheduler`'s root; the decorator is reachable only via
  `shared_core.scheduler.decorators.cron`. Verified concretely (`sn.cron
  is sn.cron` resolves to the submodule) before finalizing `__init__.py`,
  not just reasoned about.
- **Distributed coordination reuses Prompt 019's Redlock-principled
  `DistributedLock` for three distinct purposes**, kept in three
  separate modules rather than one: `locking.py` (per-job exclusive
  execution, TTL keyed to the job's own timeout), `leader.py` (cluster
  leadership, one lock key shared by every node), and (indirectly)
  `heartbeat.py`/`failover.py` (liveness, via plain TTL'd keys rather
  than the lock's ownership-token machinery, since a heartbeat has no
  "owner" to protect against, only a presence to expire).
- **`Worker` accepts an optional composed `handler` instead of always
  calling `executor.execute` directly**: without this, `middleware.py`'s
  `apply_middleware()`/`ExecuteHandler` chain would have had no way to
  actually wrap execution -- dead, unintegrated code. `Worker.__init__`
  defaults `handler` to `executor.execute` when none is given, so every
  existing test and the common case stay unchanged; a caller that wants
  the full middleware chain passes a pre-composed handler instead.
- **`SchedulerManager.dispatch_due_jobs()` owns the leader-only
  due-job-to-queue handoff**: `SchedulerEngine.due_jobs()` only
  computes *which* jobs are due (pure, no side effects); only
  `SchedulerManager`, which also holds the optional `LeaderElection`,
  decides whether *this node* is allowed to act on that list right now.
  Keeps the "Split-Brain Prevention" check in exactly one place.
- **`HistoryEntry` has no "Output"/"Logs" field**: docs/026 "HISTORY"
  names them, but a job's `fn` (per `JobFn = Callable[[Job],
  Awaitable[None]]`) returns nothing and this framework defines no
  output channel -- a job's own logging already goes through
  `shared_core.logging`. Documented as an intentional omission rather
  than a fabricated always-empty field.
- **No real bugs surfaced during testing this prompt** (unlike Prompts
  023-025, each of which caught at least one genuine defect via
  integration testing): every module's test batch passed on its first
  real run against `FakeAsyncRedis` and the actual RabbitMQ container.
  Two design bugs were still caught and fixed before writing tests, by
  re-reading the code: `Worker._record_result` would have marked a
  lock-skipped job `FAILED` (fixed by checking `attempts == 0` first),
  and `compute_next_run`'s original `match`-statement shape exceeded
  Ruff's branch/return complexity limits (refactored into a
  per-`ScheduleType` handler dispatch table).
- **No circular imports**: `scheduler -> queue` (cron computation,
  retry policy, durable delivery), `scheduler -> cache` (distributed
  locking), `scheduler -> monitoring` (health checks/status rollup),
  `scheduler -> telemetry` (root tracing), and `scheduler -> logging`
  (audit, correlation context) are all safe and one-directional -- none
  of those packages depend on `scheduler`.
- **No new dependencies**: every distributed-coordination and
  scheduling primitive this framework needed already existed
  (`shared_core.cache.locks`, `shared_core.queue.scheduler`,
  `shared_core.queue.retry`) or is in the stdlib (`zoneinfo` for
  timezone/DST handling).
