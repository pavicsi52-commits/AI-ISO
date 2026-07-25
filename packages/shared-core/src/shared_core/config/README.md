# Enterprise Configuration Framework

Every AI-IOS service loads its configuration through this package. No
service reads `os.environ` directly.

## Configuration Guide

```python
from shared_core.config import get_settings

settings = get_settings()
settings.database.dsn      # SQLAlchemy async DSN
settings.redis.url         # Redis connection URL
settings.email.email_enabled
```

`get_settings()` returns a process-wide cached `Settings` instance
aggregating every section (Application, Database, Redis, RabbitMQ, Neo4j,
MinIO, OpenSearch, Auth, Monitoring, Telemetry, Storage, Email,
Notifications, Scheduler, AI, Automation, Inventory, Validation, Secrets).

For one-off, untyped lookups (e.g. a value a future section hasn't been
added for yet), use the Configuration API instead:

```python
from shared_core.config import get, get_bool, get_int, get_list, exists

get("database_host")                 # raw value, any section
get_int("database_port", default=5432)
get_bool("email_enabled")
exists("ai_api_key")
```

`get_string` / `get_bool` / `get_int` / `get_float` / `get_list` /
`get_dict` raise `MissingVariableError` if the key isn't set and no
`default` is given, and `InvalidTypeError` if the raw value can't be
coerced to the requested type.

## Environment Guide

Six environments are supported: `local`, `development`, `testing`, `ci`,
`staging`, `production` (`shared_core.config.Environment`). The active
environment is detected from `AIIOS_ENVIRONMENT`, defaulting to
`development`.

Load order (each stage overrides the one before it):

1. **Default** -- each field's declared default.
2. **Environment** -- `.env`, then `.env.<environment>`, then `.env.local`
   (each layered on top of the last), plus OS environment variables, which
   pydantic-settings already prioritizes over any dotenv file.
3. **Secrets** -- `AIIOS_<NAME>_FILE`, then `/run/secrets/<name>` (Docker
   Secrets / Kubernetes Secrets), for any field that looks like a secret
   (`password`, `secret`, `key`, or `token` in its name).
4. **Runtime Overrides** -- explicit keyword arguments to `load_settings()`,
   e.g. `load_settings(database_password="test")` in tests.

Vault, AWS Secrets Manager, and Azure Key Vault are future secret backends
(`SecretsSettings.secrets_backend` is reserved to select one).

## Developer Guide

- `get_settings()` / `reload_settings()` / `clear_settings_cache()` --
  process-wide cache, optionally TTL-bounded via `configure_cache_ttl()`.
- `ConfigWatcher` -- polls the active environment's dotenv files and calls
  `reload_settings()` when they change. A no-op outside `local` and
  `development` (`Environment.allows_hot_reload`); never runs in
  production.
- `validate_settings(settings)` -- cross-section checks that only make
  sense once every section is loaded together (e.g. required secrets in
  production). Not called automatically by `load_settings()`; call it
  explicitly at service startup.
- All configuration exceptions (`InvalidConfigurationError`,
  `MissingVariableError`, `InvalidTypeError`, `MissingSecretError`,
  `UnknownEnvironmentError`, `CircularConfigurationError`) subclass
  `shared_core.exceptions.ConfigurationError`, so a bare
  `except ConfigurationError` still catches all of them.

## Migration Guide

Code written against the Prompt 012 baseline (`shared_core.config.manager`)
should switch to `shared_core.config.loader`, which replaces it 1:1
(`Settings`, `load_settings`) and adds `env_files_for`. Everything else
(`get_settings`, `reload_settings`, `clear_settings_cache`, `Environment`,
`resolve_secret`, `validate_settings`, every `*Settings` section class) is
unchanged and still importable from `shared_core.config` directly.
