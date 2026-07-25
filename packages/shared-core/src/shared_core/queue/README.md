# Enterprise Queue Framework

The reusable job-queue/background-processing backbone for AI-IOS
(docs/021_Enterprise_Queue_Framework.md.txt "OBJECTIVE"): Job Queue,
Background Processing, Task Scheduling, Retry, Priority Queue, Dead
Letter Queue, Delayed Queue, Worker Pool, Queue Monitoring, Queue
Metrics, Queue Health, Distributed Processing. RabbitMQ today; provider
abstraction (a framework-local `ExchangeType`, a format-agnostic message
envelope) keeps a future Kafka/NATS/Redis Streams backend from requiring
a public API change.

`shared_core.events` (Prompt 020) is built on top of this package, not
the other way around -- `QueueManager` is "the only place any service
talks to RabbitMQ directly" (docs/012), and everything else here is a
higher-level convenience layered on top of it.

## Developer Guide

```python
from shared_core.config.settings import RabbitMQSettings
from shared_core.queue import create_queue_framework

framework = await create_queue_framework(RabbitMQSettings())
await framework.manager.declare_queue_with_dlq("orders.created")

async def handler(message: dict) -> None:
    ...

await framework.consumer.subscribe("orders.created", handler)
await framework.producer.publish("orders.created", {"order_id": "123"})
await framework.shutdown()
```

`create_queue_framework()` is the one call a service's startup makes: it
connects with retry ("Connection Management"), and hands back a
`QueueFramework` bundling the connection, `QueueManager`, `Producer`,
`Consumer`, and an empty `TaskScheduler`.

### Producer and Consumer

```python
from shared_core.queue import Producer, Consumer

await producer.publish(queue_name, message, priority=Priority.HIGH)
await producer.publish_batch(queue_name, messages)
task = producer.publish_async(queue_name, message)          # fire-and-forget
await producer.publish_scheduled(queue_name, message, at=some_datetime)

await consumer.subscribe(queue_name, handler, filter=lambda m: m["type"] == "x")
await consumer.subscribe_batch(queue_name, batch_handler, batch_size=50)
```

`QueueManager.publish()`/`consume()` already provide "Confirmation" (a
publish doesn't return until the broker accepts it) and
acknowledgement/reject/requeue/retry/dead-letter mechanics; `Producer`
adds retry-with-backoff, a publish deadline, batching, async scheduling,
and time-delayed publish; `Consumer` adds message filtering and batch
delivery -- the two docs/021 "CONSUMER" features `QueueManager.consume`
doesn't already cover.

### Retry and Dead Letter

```python
from shared_core.queue import RetryPolicy
from shared_core.queue.dead_letter import inspect_dead_letters, replay_dead_letters, filter_dead_letters

policy = RetryPolicy(max_attempts=5, backoff_base_seconds=1.0, backoff_multiplier=2.0)
await queue_manager.consume(queue_name, handler, retry_policy=policy)

await inspect_dead_letters(queue_manager, queue_name)                       # peek, non-consuming
await filter_dead_letters(queue_manager, queue_name, lambda p: p["urgent"])
await replay_dead_letters(queue_manager, queue_name)                        # back onto the original queue
```

**Retry classification defaults to permissive**: unless a raised
exception carries an explicit `retryable = False` attribute (every
`AIIOSException` subclass does), *any* exception is treated as worth
retrying -- a generic queue consumer's handler is arbitrary business
logic the framework has no way to know is safely retryable or not.
Retries are delayed (not requeued immediately): a failed message is
routed through a TTL-based holding queue (see "Delayed Jobs" below)
computed from the backoff curve, so a retrying consumer never hot-loops
against a still-failing dependency.

### Priority Queues

```python
from shared_core.enums.priority import Priority
from shared_core.queue.priority import declare_priority_queue

await declare_priority_queue(channel, queue_name)  # x-max-priority queue
await producer.publish(queue_name, message, priority=Priority.CRITICAL)
```

Five levels -- `CRITICAL`, `HIGH`, `NORMAL`, `LOW`, `BACKGROUND` -- map
to RabbitMQ's native `x-max-priority` queue argument (0-9 internally).

### Delayed Jobs

```python
from datetime import UTC, datetime, timedelta
from shared_core.queue.delay import declare_delay_queue, delay_until

delay_ms = delay_until(datetime.now(UTC) + timedelta(minutes=5))
holding_name = await declare_delay_queue(channel, queue_name, delay_ms)
await queue_manager.publish(holding_name, message)  # arrives on queue_name after 5 minutes
```

RabbitMQ has no native per-message delay without the
`rabbitmq-delayed-message-exchange` community plugin (not installed
here). Implemented instead with the standard TTL + dead-letter pattern:
one holding queue per distinct delay duration (never consumed directly,
just a queue-level `x-message-ttl` + `x-dead-letter-routing-key` back to
the real queue), so every message in a given holding queue shares the
same TTL -- avoiding the well-known "head-of-queue" expiry-ordering quirk
classic queues have when messages in the same queue carry different TTLs.

### Task Scheduling

```python
from shared_core.queue.scheduler import ScheduledTask, TaskScheduler

scheduler = TaskScheduler()
scheduler.register(ScheduledTask(name="nightly-report", fn=run_report, cron_expression="0 2 * * *"))
ran = await scheduler.run_due()  # call this on your own poll interval, e.g. from a WorkerPool worker
```

Pure due-task tracker -- callers drive it on their own interval rather
than it owning an event loop or timer itself. "After Time"/"Specific
Date" one-shot scheduling is `Producer.publish_scheduled`/
`shared_core.queue.delay` directly; this module is specifically "Cron"/
"Recurring".

### Worker Pool

```python
from shared_core.queue.worker import WorkerBase, WorkerPool

class MyWorker(WorkerBase):
    queue_name = "orders.created"
    async def handle(self, message: dict) -> None: ...

pool = WorkerPool(lambda: MyWorker(queue_manager), name="orders-pool", min_workers=2, max_workers=10)
await pool.start()
await pool.scale_to(5)
pool.status()          # per-worker running/restart_count/last_heartbeat
await pool.shutdown()
```

Each pool worker is one independent consumer registration on its own
channel (its own prefetch window) -- running *N* gives *N* times the
effective concurrency. The underlying `aio-pika` robust connection
already transparently reconnects and re-declares a dropped consumer on
its own; this pool's "Worker Restart" supervises the *outer* failure a
robust reconnect can't fix by itself (the worker's own `start()` call
raising), re-instantiating and re-registering that worker after backoff.

### Routing

```python
from shared_core.queue.exchange import ExchangeType, declare_exchange
from shared_core.queue.routing import Router, build_routing_key, topic_matches

exchange = await declare_exchange(channel, "aiios.events", ExchangeType.TOPIC)
key = build_routing_key("asset", "discovered", "gpu")   # "asset.discovered.gpu"
topic_matches("asset.*", "asset.discovered")             # True (client-side dry run)

router: Router[str] = Router()
router.add_rule("asset.*", "asset-queue")
router.resolve("asset.discovered")                        # ["asset-queue"]
```

### Health and Metrics

```python
from shared_core.queue.health import check_queue_health, get_queue_depth

report = await check_queue_health(connection, statistics=queue_manager.statistics)
depth = await get_queue_depth(queue_manager, queue_name)
```

Prometheus metrics (`shared_core.queue.metrics`) are instrumented
directly inside `QueueManager` -- every publish/consume/retry/dead-letter
through *any* caller is counted automatically, labeled by the message's
actual queue name (`queue_messages_published_total`/`consumed_total`/
`failed_total`/`dead_lettered_total`, reused from
`shared_core.metrics.standard` since Prompt 012; `events_retried_total`
and processing-time/worker-count/queue-depth are new).

## Architecture Notes

- **`client.py` renamed to `connection.py`** (matching this prompt's own
  directory listing), expanded with Connection Pool, Reconnect, Retry,
  Heartbeat, Health Check, Graceful Shutdown, TLS, Authentication.
- **`consumer.py` was Prompt 012's baseline module name for what's now
  `manager.py`'s `QueueManager.consume`** -- docs/021 uses `consumer.py`
  for a *different*, higher-level thing (the `Consumer` facade), so this
  is a fresh file, not a rename; `manager.py` keeps owning the actual
  RabbitMQ protocol interaction.
- **No circular imports**: `queue -> cache` (compression, encryption) is
  safe and one-directional -- `cache` has no dependency on `queue`.
  `events -> queue` (unchanged from Prompt 020) stays one-directional too.
- **Metrics ownership moved down a layer from Prompt 020**: `events/metrics.py`
  used to record `queue_messages_*_total` itself (the queue layer didn't
  instrument them yet at the time). Now that `QueueManager` does, those
  calls were removed from the events layer to avoid double-counting;
  `events/metrics.py` keeps only what's genuinely event-specific
  (publish/consume latency measured at the `EventManager` boundary,
  event-replay counts, and `record_internal_failure` for
  `InternalEvent`s, which never reach `QueueManager` at all).
- **Retry classification defaults to permissive**, not restrictive --
  see "Retry and Dead Letter" above. This intentionally differs from
  `shared_core.events.retry`'s stricter default (only
  connection/timeout-shaped exceptions retry by default there), because
  events publish failures are typically genuinely transient-or-not in a
  way a generic queue consumer's arbitrary handler code isn't.
