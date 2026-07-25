# shared-core

The Enterprise Shared Core Framework. Every AI-IOS microservice depends on
this package instead of re-implementing cross-cutting concerns.

## Scope

Per [`docs/012_Shared_Core_Framework.md.txt`](../../docs/012_Shared_Core_Framework.md.txt),
this package provides a *basic, working* implementation across every
cross-cutting concern (configuration, exceptions, validation, security,
logging, database, cache, events, queue, storage, monitoring, telemetry) plus
fully-built-out constants, enums, base models, request/response schemas,
middleware, decorators, interfaces, types, and helpers.

Eight of those concerns get their own deep-dive specification later, which
expands the basic Prompt 012 implementation into the full framework:

| Concern | Deep-dive prompt |
|---|---|
| `config/` | `docs/013_Configuration_Framework.md.txt` |
| `logging/` | `docs/014_Enterprise_Logging_Framework.md.txt` |
| `exceptions/` | `docs/015_Enterprise_Exception_Framework.md.txt` |
| `validators/` | `docs/016_Enterprise_Validation_Framework.md.txt` |
| `security/` | `docs/017_Enterprise_Security_Framework.md.txt` |
| `database/` | `docs/018_Enterprise_Database_Framework.md.txt` |
| `cache/` | `docs/019_Enterprise_Cache_Framework.md.txt` |
| `events/` | `docs/020_Enterprise_Event_Framework.md.txt` |

`constants/`, `enums/`, `base/`, `models/`, `schemas/`, `requests/`,
`responses/`, `middleware/`, `storage/`, `monitoring/`, `metrics/`,
`telemetry/`, `utils/`, `helpers/`, `decorators/`, `interfaces/`, and
`types/` are fully built out in Prompt 012 and are not revisited by a later
prompt.

## Layout

Standard `src` layout — the importable package is `shared_core`
(`src/shared_core/`), not `shared-core` (the PyPI/directory name uses a
hyphen per repository convention; Python package names cannot contain
hyphens).

## Testing

```bash
uv run pytest --cov=src/shared_core --cov-report=term-missing
```

Target: ≥95% coverage per `docs/012_Shared_Core_Framework.md.txt`.
