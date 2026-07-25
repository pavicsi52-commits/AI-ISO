# Enterprise Telemetry Framework

Complete end-to-end observability for AI-IOS
(docs/024_Enterprise_Telemetry_Framework.md.txt "OBJECTIVE"): Distributed
Tracing, OpenTelemetry Integration, Context Propagation, Span Management,
Correlation IDs, Request IDs, Performance Profiling, Trace Analytics,
Metrics Correlation, Log Correlation, Trace Export, Trace Search,
Performance Baselines.

Builds on top of, and deliberately does not duplicate, the logging
(`shared_core.logging`), monitoring (`shared_core.monitoring`), and
metrics (`shared_core.metrics`) frameworks -- trace/span IDs flow into
the *same* `LogContext` Prompt 014's logger already reads, not a second,
parallel context store.

## Developer Guide

```python
from shared_core.config.settings import TelemetrySettings
from shared_core.telemetry import create_telemetry_framework

manager = create_telemetry_framework(TelemetrySettings(), environment="production")

with manager.start_root_trace("checkout"):
    ...  # everything nested here shares one trace

manager.shutdown()  # flush and close at service shutdown
```

`create_telemetry_framework()` is the one call a service's startup
makes: it builds a tracer provider (batched export, a configured
sampler) and hands back a `TelemetryManager`.

### Spans and Root Traces

```python
from shared_core.telemetry import get_tracer, start_root_trace, start_span, SpanType

tracer = get_tracer(__name__)

with start_root_trace(tracer, "nightly-report"):        # no parent -- an entry point
    with start_span(tracer, "step-1", span_type=SpanType.WORKFLOW_STEP):
        ...
```

Every span shall have a parent (docs/024 "TELEMETRY PRINCIPLES") --
`start_span` always attaches under whatever is currently active;
`start_root_trace` is the one deliberate exception, detaching first so a
new trace never accidentally nests under leftover context from
unrelated prior work.

### Per-Subsystem Span Helpers

```python
from shared_core.telemetry.database import trace_database_query
from shared_core.telemetry.cache import trace_cache_access
from shared_core.telemetry.queue import trace_queue_publish, trace_queue_consume
from shared_core.telemetry.ai import trace_ai_request, trace_model_inference
# ...and storage.py, connector.py, plugin.py, workflow.py, automation.py, validation.py

async with trace_database_query(tracer, "select", table="orders"):
    ...
```

One thin context manager per docs/024 "SPAN TYPES" entry, all built on
the same `span.start_span` primitive -- attribute masking ("SECURITY":
never capture secrets) is applied consistently in exactly one place
rather than once per subsystem.

### Decorators

```python
from shared_core.telemetry.decorators import trace, span, measure, track_database, track_ai

@track_database(tracer)
async def get_user(user_id: str) -> User: ...

@measure(some_histogram)
async def do_work() -> None: ...
```

`@trace`/`@span`/`@measure`/`@profile`/every `@track_*` decorator --
async-only, matching this codebase's async-first convention. **Naming
note**: `@trace`/`@span` are only importable from
`shared_core.telemetry.decorators` directly, not re-exported at the
package root, since they'd otherwise shadow this package's own
`trace`/`span` *submodules* of the same name (see Architecture Notes).

### Context Propagation

```python
from shared_core.telemetry.propagation import inject_context, extract_context, use_context, restore_context

headers = inject_context()                     # outbound: HTTP call, queue publish, ...
context = extract_context(incoming_headers)     # inbound: HTTP request, queue consume, ...
token = use_context(context)
try:
    ...
finally:
    restore_context(token)
```

W3C Trace Context (`traceparent`/`tracestate`) via the OpenTelemetry
SDK's own propagator -- one `dict[str, str]` carrier covers every
transport docs/024 "CONTEXT PROPAGATION" lists (HTTP headers, queue
message headers, background job/scheduler metadata); `queue.py`'s
`trace_queue_publish`/`trace_queue_consume` and `worker.py`'s
`trace_background_job`/`scheduler.py`'s `trace_scheduler_job` wrap this
directly so a worker's first span continues its publisher's trace
rather than starting an unrelated one.

### Middleware

```python
from shared_core.telemetry.middleware import TracingMiddleware

app.add_middleware(TracingMiddleware, tracer=tracer)
```

Raw ASGI (matching `shared_core.middleware.timing.TimingMiddleware`'s
shape), extracting an inbound `traceparent` header first so this
service's span continues an upstream gateway's trace.

### Sampling

```python
from shared_core.telemetry.sampling import (
    always_sample, never_sample, probability_sampler,
    environment_based_sampler, RuleBasedSampler, DynamicSampler, AdaptiveSampler,
)
```

Every strategy docs/024 "SAMPLING" lists, built on the OpenTelemetry
SDK's own `Sampler` protocol. `DynamicSampler.set_ratio()` changes the
ratio at runtime; `AdaptiveSampler` scales its own ratio down under load
to approach a target traces/second throughput.

### Exporters

```python
from shared_core.telemetry.exporters import create_exporter

exporter = create_exporter("otlp", otlp_endpoint="http://collector:4318/v1/traces")
```

`console`, `json` (a small newline-delimited-JSON file exporter this
framework writes itself -- the SDK ships Console and OTLP but no JSON
file writer), and `otlp` (a real collector). Jaeger/Tempo/Zipkin/Azure
Monitor/AWS X-Ray/Google Cloud Trace are explicitly "Future" per
docs/024, not implemented -- and this framework must never run a
Jaeger/Tempo/Prometheus *server* itself ("DO NOT IMPLEMENT").

### Analytics

```python
from shared_core.telemetry.analytics import TraceRecorder, AnalyticsSpanProcessor

recorder = TraceRecorder()
provider.add_span_processor(AnalyticsSpanProcessor(recorder))

recorder.slowest_traces(n=10)
recorder.error_hotspots()
recorder.percentile_latency_ms(95)
recorder.service_dependency_graph()
```

Purely in-process (this framework must not run a Jaeger/Tempo server) --
a bounded, process-lifetime buffer of recently completed traces, fed by
a real `SpanProcessor` hook rather than requiring callers to manually
record anything. A service wanting trace history across a fleet,
surviving a restart, should query its OTLP collector's own backend, not
this module.

### Metrics Correlation

```python
from shared_core.telemetry.metrics import observe_with_trace_exemplar, database_time_seconds

observe_with_trace_exemplar(database_time_seconds, elapsed_seconds, operation="select")
```

Most of docs/024 "METRICS COLLECTION" already has a real Prometheus
instrument elsewhere (Request Count/Latency: Prompt 012; Queue Size/
Worker Count: Prompt 021; Workflow/Automation/Validation/Inference
Duration: Prompt 023) -- `observe_with_trace_exemplar` is what's
genuinely new: attaches the *current trace's* ID to any histogram
observation as a Prometheus exemplar.

### Log Correlation

Already working as of Prompt 014 -- `shared_core.logging.formatter`
reads `trace_id`/`span_id` from the active OpenTelemetry span into every
structured log record automatically. `logs.correlate_logs_with_span`
only matters when a span isn't the *ambient* current one (a queue
consumer processing a message on an extracted, not locally-current,
context).

## Architecture Notes

- **`trace`/`span` naming collision, resolved by scope**: docs/024 names
  both a `trace.py`/`span.py` file *and* a `@trace`/`@span` decorator
  identically. The package `__init__.py` keeps the submodules' bare
  names (`get_tracer`, `start_root_trace`, `SpanType`, `start_span`)
  since they're this framework's foundation; the two decorators stay
  reachable only via `shared_core.telemetry.decorators.trace`/`.span`,
  never re-exported at the package root, so `shared_core.telemetry.trace`
  unambiguously always means the submodule.
- **No circular imports**: `telemetry -> logging` (reading/writing
  `LogContext`) is safe and one-directional -- `logging` has no
  dependency on `telemetry`. `checks.py`-style adapters were considered
  for `database`/`cache`/`queue` health but telemetry's per-subsystem
  files (`database.py`, `cache.py`, `queue.py`, ...) are pure span
  helpers with **zero** import of those packages -- a caller wraps its
  own call, so no dependency edge exists in either direction.
- **Was Prompt 012's baseline `tracing.py`**, split along this prompt's
  own file boundaries: `configure_tracing` moved to `provider.py`
  (provider/resource/exporter setup), `get_tracer` to `trace.py`
  (tracer access, root traces), `start_span` to `span.py` (span
  creation, now also owning `SpanType` and attribute masking).
- **`AnalyticsSpanProcessor` resolves service identity on `on_start`,
  not `on_end`**: nested spans *end* in the reverse order they started
  (innermost first), so a child span's `on_end` -- needing its parent's
  service already resolved for the dependency graph -- would otherwise
  almost always run before the parent ever recorded itself. Found while
  writing the dependency-graph test, not by inspection.
- **New dependency**: `opentelemetry-exporter-otlp-proto-http`, for
  `exporters.py`'s real OTLP exporter (the SDK/API packages were already
  present from Prompt 012, but no exporter package had been added yet).
