# Enterprise Event Framework

The event-driven communication backbone for AI-IOS
(docs/020_Enterprise_Event_Framework.md.txt "OBJECTIVE"): Event
Publishing, Event Consumption, Event Routing, Event Store, Event Replay,
Dead Letter Handling, Event Versioning, Event Validation, Event
Monitoring. Built on top of `shared_core.queue` (Prompt 012), which
remains the only module that talks to RabbitMQ directly -- this package
never reimplements broker transport, only what sits above it: typed
event envelopes, a registry, routing/dispatch, retry-with-backoff,
replay, and audit/metrics.

## Developer Guide

```python
from shared_core.config.settings import RabbitMQSettings
from shared_core.events import create_event_framework, DomainEvent
from typing import ClassVar

class WidgetCreated(DomainEvent):
    event_name: ClassVar[str] = "WidgetCreated"
    widget_name: str

framework = await create_event_framework(RabbitMQSettings())

async def on_widget_created(event: WidgetCreated) -> None:
    ...

await framework.manager.subscribe("WidgetCreated", on_widget_created)
await framework.manager.publish(WidgetCreated(source_service="widget-service", widget_name="thing"))
await framework.shutdown()
```

`create_event_framework()` is the one call a service's startup makes: it
opens the RabbitMQ connection and hands back an `EventFramework` bundling
the connection, `QueueManager`, and `EventManager` -- the facade every
publish/subscribe call actually goes through.

### Event Types

```python
from shared_core.events import BaseEvent, DomainEvent, IntegrationEvent, InternalEvent, EventType
```

Every event is one of `EventType`'s 14 values; three get their own base
class per docs/020's deep-dive sections:

- **`DomainEvent`** -- a business fact (`UserCreated`, `AssetDiscovered`).
  Published/consumed like any other queue-backed event.
- **`IntegrationEvent`** -- used between microservices. Payloads must be a
  deliberate, versioned public contract -- never a serialized ORM entity.
- **`InternalEvent`** -- "Never leave the owning service," enforced
  *structurally*, not just documented: `EventBus` routes it through an
  in-process `EventDispatcher` only, never through the queue-backed
  `EventPublisher`. There is no code path by which one could reach
  RabbitMQ.

Every event auto-populates `organization_id`/`project_id`/`user_id`/
`correlation_id`/`request_id` from the currently-bound request context
(`shared_core.security.context`/`shared_core.logging.context`) --
publishing code doesn't thread tenant/correlation IDs through by hand.

### Event Registry and Versioning

```python
from shared_core.events import EventRegistry, default_registry

default_registry.register(WidgetCreated)
default_registry.lookup("WidgetCreated")            # latest registered version
default_registry.lookup("WidgetCreated", "v1")       # a specific version
default_registry.supported_versions("WidgetCreated")  # ["v1", "v2", ...]
```

Every event name maps to *every version* registered under it (docs/020
"EVENT VERSIONING": "Support v1/v2/v3"). A `VersionMigrator` chains
payload-upgrade functions (`v1->v2->v3`) so a consumer that only
understands the latest shape can still process an older stored event --
`deserialize_event(data, migrator=..., target_version=...)` migrates the
payload forward and validates it against the *target* version's class.

### Publishing and Subscribing

```python
from shared_core.events import EventManager

await manager.publish(event, required_permission=Permission.CREATE)
await manager.subscribe("WidgetCreated", handler, priority=100, filter=lambda e: e.source_service == "x")
```

`EventManager` is the facade: every `publish()` validates (schema,
version, payload, metadata, tenant, permissions), meters, and audits;
every `subscribe()` wraps the handler with the same metering/audit, and
routes internal-vs-everything-else through `EventBus`. Extend the
pipeline via `manager.middleware.use_publish()`/`use_consume()`
(`MiddlewareChain`, onion-style, first-registered runs outermost) for
cross-cutting concerns beyond the built-in validate/meter/audit baseline.

Retry backoff (`RetryPolicy`, exponential + jitter) is layered *on top
of* `QueueManager.consume()`'s existing count-based retry/dead-letter
mechanism -- `EventSubscriber` sleeps before re-raising a retryable
failure, but the queue manager still owns the actual requeue/dead-letter/
ack decision.

### Dead Letter Handling

```python
from shared_core.events.dead_letter import inspect_dead_letters, replay_dead_letters, purge_dead_letters

await inspect_dead_letters(queue_manager, "WidgetCreated")  # peek, doesn't consume
await replay_dead_letters(queue_manager, "WidgetCreated")   # re-publish onto the original queue
await purge_dead_letters(queue_manager, "WidgetCreated")    # permanently delete
```

Moving a failed message to its dead-letter queue is already automatic
(`QueueManager.declare_queue_with_dlq`, Prompt 012); this module is what
acts on what's already there.

### Replay by Criteria

```python
from shared_core.events.replay import EventStore, ReplayCriteria, replay_events

store = EventStore(redis_client)  # append this alongside every publish, e.g. via a publish middleware
count = await replay_events(store, publisher, ReplayCriteria(
    organization_id=org_id, event_name="WidgetCreated", start_time=..., end_time=...,
))
```

RabbitMQ queues are FIFO with no historical-query capability, so
"Replay by Time Range/Organization/Project/Service/Event Type/
Correlation ID" (docs/020) needs its own index. `EventStore` is a
bounded, self-trimming Redis sorted-set timeline (raw `ZADD`/
`ZRANGEBYSCORE`/`ZREMRANGEBYSCORE`, not `CacheManager`, which doesn't
expose sorted sets) -- every `append()` also prunes anything older than
`retention_seconds`, so the index needs no separate cleanup job.

### Routing and Dispatch

```python
from shared_core.events.router import EventRouter
from shared_core.events.dispatcher import EventDispatcher

router: EventRouter[str] = EventRouter()
router.add_route("Widget*", "widget-queue")
router.resolve("WidgetCreated")  # ["widget-queue"] -- fans out to every matching pattern

dispatcher = EventDispatcher()
dispatcher.register("CacheWarmed", handler, priority=50, filter=lambda e: ...)
await dispatcher.dispatch(event)  # priority order; every handler runs even if one raises
```

`EventRouter` is a small, generic glob-pattern (`fnmatch`) resolver, kept
separate from `EventDispatcher` (which decides which *handlers* run for
an already-resolved target) so a router can also resolve to non-handler
targets. `EventBus` uses `EventDispatcher` internally for internal
events; most callers only ever touch `EventManager`.

### Audit and Metrics

Every publish/consume/replay/failure is audited via
`shared_core.logging.logger.AIIOSLogger.audit()` (never a business
table), payloads masked through
`shared_core.logging.filters.mask_payload` first. Metrics reuse
`shared_core.metrics.standard.queue_messages_published_total`/
`consumed_total`/`failed_total`/`dead_lettered_total` (defined since
Prompt 012, first actually instrumented here), labeled by the event's
real queue name (`events.<event_name>`) -- what an operator sees in
RabbitMQ's own management UI -- plus new `events_retried_total`/
`events_replayed_total` counters and publish/consume latency histograms.

### Health

```python
from shared_core.events.health import check_event_framework_health

report = await check_event_framework_health(connection, registry=default_registry)
# report.status, .latency_ms, .registered_event_count, .connection_closed
```

## Architecture Notes

- **`DO NOT IMPLEMENT: RabbitMQ`** (docs/020): this package never talks
  to RabbitMQ directly or reimplements broker transport, retry counting,
  or dead-letter routing -- all of that stays owned by
  `shared_core.queue.manager.QueueManager` (Prompt 012). Everything here
  (`retry.py`, `dead_letter.py`, `subscriber.py`) layers *on top of* that
  existing mechanism.
- **`consumer.py` renamed to `subscriber.py`** (`EventConsumer` ->
  `EventSubscriber`) to match this prompt's own directory listing.
- **`InternalEvent`'s "never leave the owning service" is structural**,
  not just documented -- see "Event Types" above.
- **Event replay's `EventStore` uses a direct Redis client, not
  `CacheManager`** -- sorted sets aren't part of `CacheManager`'s
  abstraction, and reimplementing that abstraction just to add one
  primitive wasn't worth the indirection.
- **`shared_core.events.validator` doesn't reuse `shared_core.validation`'s
  9-layer pipeline** (Prompt 016) -- that framework is shaped around
  request/response/field validation, not an event envelope; it does
  reuse `shared_core.security.rbac.has_permission` and
  `shared_core.logging.filters.mask_payload`, the primitives Prompt
  016/014 already built for exactly this.
- **No circular imports**: `events -> cache` (for `EventStore` and
  payload compaction) and `events -> security`/`events -> validation`
  are all one-directional; nothing in `cache`, `security`, or
  `validation` imports from `events`.
