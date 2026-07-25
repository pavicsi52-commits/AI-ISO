# Enterprise Exception Framework

Every custom exception raised anywhere in AI-IOS inherits from
`AIIOSException`. No service defines its own exception hierarchy or
handling mechanism.

## Exception Hierarchy

```
AIIOSException (base.py)
├── AuthenticationError        AIIOS-AUTH-*        401
├── AuthorizationError         AIIOS-AUTHZ-*        403
├── ValidationError            AIIOS-VAL-*          400
├── DatabaseError              AIIOS-DB-*           500  (retryable)
├── ConfigurationError         AIIOS-CONFIG-*       500
├── DependencyError            AIIOS-DEP-*          503  (retryable)
├── StorageError                AIIOS-STORAGE-*      503  (retryable)
├── QueueError                  AIIOS-QUEUE-*        503  (retryable)
├── CacheError                  AIIOS-CACHE-*        503  (retryable)
├── NetworkError                 AIIOS-NETWORK-*      503  (retryable)
├── WorkflowError                AIIOS-WORKFLOW-*     500
├── AutomationError              AIIOS-AUTO-*         500
├── InventoryError                AIIOS-INVENTORY-*    500
├── MonitoringError                AIIOS-MONITORING-*  500
├── SchedulerError                  AIIOS-SCHEDULER-*  500
├── AIError                          AIIOS-AI-*        502  (retryable)
├── NotificationError                 AIIOS-NOTIFICATION-*  502  (retryable)
├── EventError                         AIIOS-EVENT-*   500
├── BusinessRuleError                   AIIOS-BIZ-*    422
├── AIIOSTimeoutError                    AIIOS-TIMEOUT-* 504  (retryable)
├── ConflictError                         AIIOS-CONFLICT-* 409
├── NotFoundError                          AIIOS-NF-*   404
├── RateLimitError                          AIIOS-RATE-* 429  (retryable)
├── InternalError                            AIIOS-INTERNAL-*  500
├── ExternalError                             AIIOS-EXTERNAL-* 502  (retryable)
└── UnknownError                                AIIOS-UNKNOWN-*  500
```

Every subclass sets `error_code`, `status_code`, `severity`
(`low`/`medium`/`high`/`critical`), `retryable`, and `default_user_message`
as class attributes.

## Error Code Catalog

`shared_core.exceptions.ERROR_CODE_CATALOG` maps every registered
`AIIOS-<DOMAIN>-<NUMBER>` code to its exception class, built (and
validated for uniqueness and format) at import time from
`shared_core.exceptions.ALL_EXCEPTION_CLASSES` — the single source of
truth for "every error code in the system." To see the full catalog:

```python
from shared_core.exceptions import ERROR_CODE_CATALOG
for code, cls in sorted(ERROR_CODE_CATALOG.items()):
    print(code, cls.__name__, cls.status_code, cls.severity)
```

## Usage Guide

```python
from shared_core.exceptions import NotFoundError, ValidationError

raise NotFoundError(
    f"widget id={widget_id} not found in table widgets",  # internal, logged only
    details=[f"id={widget_id}"],                            # client-safe
    user_message="The requested widget was not found.",     # optional override
)
```

If you don't pass `user_message`, the class's `default_user_message` is
used — always something safe to show a client. The internal `message` may
contain diagnostic detail (a SQL fragment, a stack context) that must
never reach an API response; that's exactly why the two are separate
fields (docs/015 "LOCALIZATION": "Store user-facing messages separately
from internal diagnostic messages").

### Automatic mapping

Don't hand-write `except` chains to classify a caught exception —
`map_exception()` does it:

```python
from shared_core.exceptions import map_exception

try:
    await session.execute(query)
except Exception as exc:
    raise map_exception(exc) from exc
```

Recognizes SQLAlchemy, Redis, aio-pika, MinIO, PyJWT, and httpx exceptions,
plus common Python builtins (`ValueError`, `KeyError`, `TimeoutError`,
`ConnectionError`, `PermissionError`). Anything unrecognized becomes
`UnknownError` rather than propagating unclassified.

### Factory

The inverse direction — given an error code (e.g. read back from a
downstream AI-IOS service's response), reconstruct the exception locally:

```python
from shared_core.exceptions import create_exception

exc = create_exception("AIIOS-NF-0001", "not found downstream")
```

## Integration Guide

Every FastAPI service registers the shared handler set once, at startup:

```python
from shared_core.exceptions import register_exception_handlers

register_exception_handlers(app)
```

This is the *only* exception handling a service registers — no
controller-level `try`/`except` translating exceptions into responses.
It handles `AIIOSException`, FastAPI's `RequestValidationError`,
`StarletteHTTPException` (so even a 404 from routing gets the standard
envelope), and `Exception` (mapped via `map_exception`) — four handlers,
one centralized mechanism.

For request-ID propagation and localization to work, also install:

```python
from shared_core.middleware import LocalizationMiddleware, RequestContextMiddleware

app.add_middleware(LocalizationMiddleware)
app.add_middleware(RequestContextMiddleware)
```

## Configuration Guide

Nothing in this package reads `shared_core.config` directly — behavior is
fixed by design (the error code catalog, HTTP mapping, and retry
classification are not meant to vary per deployment). Log *output*
(console/file/otel, level, masking) is controlled by
`shared_core.config`'s `LoggingSettings`, per
docs/014_Enterprise_Logging_Framework.md.txt.

## Troubleshooting Guide

- **My API response shows a generic message, not what I raised** — that's
  `user_message` (or `default_user_message`) by design; check the logs
  (`shared_core.exceptions` logger) for the real internal `message`.
- **A caught exception became `UnknownError`** — `map_exception()` doesn't
  recognize its type. Either map it explicitly at the call site
  (`raise SomeError(...) from caught`) or, if it's a common case, add an
  entry to `mapper.py`'s mapping.
- **`ValueError("...secret...")` leaked into the log but not the
  response** — that's correct: internal logs may contain diagnostic detail
  (never secrets by design — mask before logging anything sensitive, per
  `shared_core.logging`'s own masking), the API response never does.
- **A locale I expect doesn't get translated** — check
  `shared_core.exceptions.constants.MESSAGE_CATALOG`; only `en` (complete,
  auto-generated) and a hand-authored `es` subset exist today. An
  unmatched code always falls back to English, never to a missing key.

## Migration Guide

A service with its own local exception hierarchy and handler (as the
gateway service had, from before this package existed) should: (1) make
every custom exception a `shared_core.exceptions.AIIOSException` subclass
(or reuse one of the 26 already provided — check the catalog above before
inventing a new one), (2) delete its local exception handler module, (3)
call `register_exception_handlers(app)` once at startup instead, (4) stop
catching exceptions in individual route handlers to build error responses
by hand.
