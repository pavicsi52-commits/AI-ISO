# Enterprise Logging Framework

Every AI-IOS service uses this package instead of `print()` or a locally
configured logger.

## Usage Guide

```python
from shared_core.logging import get_logger

logger = get_logger(__name__)
logger.info("something happened", extra={"extra_fields": {"widget_id": "123"}})
logger.trace("very verbose detail")               # below DEBUG
logger.audit("user.created", actor_id="u1", resource="user:42")
logger.security("failed_login", outcome="blocked")
logger.performance("db_query", value=42.0, unit="ms")

try:
    risky()
except Exception:
    logger.exception("risky() failed")             # stdlib method, stack trace included
```

Every log line is a single JSON document carrying the full field set
(`timestamp`, `level`, `service`, `environment`, `hostname`, `request_id`,
`correlation_id`, `organization_id`, `project_id`, `user_id`, `session_id`,
`trace_id`, `span_id`, `thread_id`, `process_id`, `method`, `url`,
`status_code`, `latency_ms`, `ip_address`, `user_agent`, `message`,
`exception`) — fields that don't apply to a given call are `null`, never
omitted, so downstream log queries can rely on a stable schema.

## Integration Guide

At service startup, once configuration is loaded:

```python
from shared_core.config import get_settings
from shared_core.logging import configure_logging_from_settings

configure_logging_from_settings(get_settings())
```

This reads `Settings.logging` (level, outputs, rotation, retention,
masking) and wires up every configured output. For a FastAPI/Starlette
service, add the request logging middleware:

```python
from shared_core.logging import RequestLoggingMiddleware

app.add_middleware(RequestLoggingMiddleware)
```

This logs `request.started` (method, safe headers, payload size) and
`request.completed` (status code, latency) for every request, and binds
method/url/ip_address/user_agent so every other log line emitted while
handling that request carries them too.

Every component in a service — FastAPI routes, background workers, RabbitMQ
consumers, CLI commands, the scheduler — must call `get_logger(__name__)`
the same way; there is exactly one logger implementation in AI-IOS.

## Configuration Guide

Loaded from `shared_core.config`'s `LoggingSettings` section
(`AIIOS_LOG_*` environment variables), never read from the environment
directly by this package:

| Setting | Default | Meaning |
|---|---|---|
| `log_level` | `INFO` | `TRACE`/`DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL` |
| `log_outputs` | `console` | comma-separated: `console`, `file`, `otel` |
| `log_file_path` | `logs/app.log` | used when `file` is an output |
| `log_file_max_bytes` | 100 MB | size-based rotation threshold |
| `log_rotation_when` | `midnight` | time-based rotation interval (`TimedRotatingFileHandler` values) |
| `log_backup_count` | 30 | rotated files kept |
| `log_compress_rotated` | `true` | gzip rotated files |
| `log_retention_days` | 90 | age-based cleanup window for `cleanup_old_logs()` |
| `log_mask_enabled` | `true` | attach the sensitive-data filter to every handler |

## Troubleshooting Guide

- **A log line is missing a field I expect** — every field in "LOG FORMAT"
  is always present (possibly `null`). If it's `null` when you expected a
  value, the relevant context wasn't bound: HTTP fields need
  `RequestLoggingMiddleware`; `trace_id`/`span_id` need an active
  OpenTelemetry span (or `bind_log_context(trace_id=..., span_id=...)`
  set manually).
- **A value I logged got replaced with `***MASKED***`** — either the field
  name matched `shared_core.constants.logging.LoggingConstants.SENSITIVE_FIELD_NAMES`
  (`password`, `secret`, `token`, `api_key`, ...), or the value looked like
  a JWT or a credit-card-shaped number sequence in free text. This is
  intentional (`log_mask_enabled=true`); disable it only for local
  debugging, never in a shared environment.
- **`otel` output raises `LogHandlerError`** — the OpenTelemetry logs SDK
  isn't installed; it's a `shared-core` dependency so this should only
  happen in an unusual environment.
- **`TRACE` messages aren't appearing** — `TRACE` is a custom level (5,
  below `DEBUG`'s 10); both the logger's own level (`logger.setLevel(...)`)
  and `log_level` in configuration must be `TRACE` or the message is
  filtered before it reaches any handler.
