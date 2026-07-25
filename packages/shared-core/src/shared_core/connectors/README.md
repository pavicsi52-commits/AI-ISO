# Enterprise Connector SDK

A unified SDK for connecting to infrastructure, operating systems,
cloud providers, virtualization platforms, industrial devices, storage
systems, networking equipment, APIs, and enterprise applications
(docs/027_Enterprise_Connector_SDK.md.txt "OBJECTIVE"): connection
management, authentication, session management, discovery, command
execution, inventory collection, validation, health monitoring, retry,
rate limiting, audit, telemetry, metrics, and plugin support.

**Scope note**: this package ships the reusable *core SDK* --
`BaseConnector` and everything around it (25 files, per docs/027
"DIRECTORY STRUCTURE" minus `providers/`). The 32 concrete provider
packages the spec also names (SSH, WinRM, Redfish, SNMP, IPMI, Docker,
Kubernetes, VMware, Proxmox, Hyper-V, OPC UA, Modbus, BACnet, MQTT,
REST, GraphQL, gRPC, SFTP, FTP, SMB, LDAP, Active Directory, DNS, NTP,
AWS, Azure, GCP, future) are a separate, later phase of work -- most
have no real target this environment can test against genuinely (no
live vCenter, Proxmox host, industrial PLC, BACnet device, or cloud
account), and each needs its own protocol client dependency. This was
an explicit, user-confirmed scoping decision for this prompt.

## Developer Guide

```python
from shared_core.connectors import (
    BaseConnector, CommandResult, ConnectorCapability, ConnectionConfig,
    ConnectorHealthReport, DiscoveryResult, InventoryReport, username_password,
    connector, ConnectorRegistry, ConnectorManager,
)

@connector("ssh")
class SshConnector(BaseConnector):
    capabilities = frozenset({ConnectorCapability.EXECUTE})

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def validate(self) -> bool: ...
    async def execute(self, command: str, **kwargs) -> CommandResult: ...
    async def health(self) -> ConnectorHealthReport: ...
    async def collect_inventory(self) -> InventoryReport: ...
    async def discover(self) -> DiscoveryResult: ...

registry = ConnectorRegistry()
registry.register_decorated(SshConnector)

manager = ConnectorManager(registry)
connector_instance = await manager.get_connector(
    "ssh", ConnectionConfig(host="10.0.0.1", port=22), username_password("admin", "hunter2"),
)
result = await connector_instance.execute("uptime")
await manager.release_connector("ssh", ConnectionConfig(host="10.0.0.1"), connector_instance)
```

Every provider inherits `BaseConnector` and follows the same
`CONNECTOR LIFECYCLE` (Register -> Initialize -> Authenticate -> Connect
-> Validate -> Execute -> Collect -> Disconnect -> Cleanup);
`ConnectorManager` pools connections per (provider, target) pair so
repeated requests to the same host reuse a live connection instead of
reconnecting every time (`pool.py`).

### Middleware

```python
from shared_core.connectors import (
    apply_middleware, logging_middleware, validation_middleware,
    metrics_collection_middleware, audit_middleware, build_retry_middleware,
    build_authentication_middleware, build_telemetry_middleware, build_security_middleware,
    OperationContext,
)

handler = apply_middleware(some_base_handler, [
    logging_middleware, validation_middleware, build_retry_middleware(),
    build_authentication_middleware(my_authenticator), metrics_collection_middleware, audit_middleware,
])
result = await handler(OperationContext(provider="ssh", target="10.0.0.1", operation="execute"))
```

The chain is generic over *any* connector operation via `OperationContext`
(not tied to `execute()`'s exact signature) -- it wraps `connect()`
(returns `None`) identically to `execute()` (returns a `CommandResult`).
Security/telemetry middleware are opt-in (need a caller-supplied
permission callback or configured `Tracer`, per docs/027 "DO NOT
IMPLEMENT": Authentication Service).

### Retry and circuit breaking

```python
from shared_core.connectors import CircuitBreaker, connector_retry_policy, build_retry_middleware

breaker = CircuitBreaker(failure_threshold=5, recovery_seconds=30)
middleware = build_retry_middleware(policy=connector_retry_policy(max_attempts=3), circuit_breaker=breaker)
```

`connector_retry_policy()` reuses `shared_core.queue.retry.RetryPolicy`
directly; `CircuitBreaker` (CLOSED -> OPEN -> HALF_OPEN) is genuinely
new to this monorepo.

### Rate limiting

```python
from shared_core.connectors import build_connector_rate_limiters

limiter = build_connector_rate_limiters(cache_manager, max_requests=10, burst=20)
status = await limiter.check_target("10.0.0.1")
```

Four independent scopes (`per_connector`/`per_target`/`per_organization`/
`per_project`), each identifier prefixed before checking so a connector
name and an organization ID with the same literal string never share a
counter.

### Health and metrics

```python
from shared_core.connectors import build_health_report, ConnectionState

report = build_health_report(connection_state=ConnectionState.CONNECTED, authenticated=True, protocol_ok=True)
report.status  # HealthStatus: worst case of connection/authentication/protocol

from shared_core.connectors import connector_latency_seconds, connector_success_total
```

## Architecture Notes

- **New `ConnectorError` exception domain**: unlike `SchedulerError`/
  `QueueError`/etc. (all pre-seeded in `shared_core.exceptions` since
  Prompt 012's baseline skeleton), no `connector.py` domain existed yet
  -- added `shared_core.exceptions.connector.ConnectorError`
  (`AIIOS-CONNECTOR-0001`) and registered it in both
  `exceptions/__init__.py` and `exceptions/constants.py`'s central
  catalog, the same way every other top-level domain base is
  registered. This package's own `exceptions.py` subclasses
  (`AIIOS-CONNECTOR-0002` onward) stay *out* of the catalog, matching
  the established "avoid a back-import cycle" precedent from every
  prior prompt's own `exceptions.py`.
- **Reuses five existing frameworks rather than reimplementing any of
  them**: `discovery.py` reuses `shared_core.monitoring.checks
  .check_tcp_reachable` (Prompt 023) for port probing; `retry.py`
  reuses `shared_core.queue.retry.RetryPolicy` (Prompt 021); `ratelimit.py`
  reuses `shared_core.cache.ratelimit.RateLimitCache` (Prompt 019);
  `health.py` reuses `shared_core.monitoring.status.calculate_status`
  (Prompt 023); `telemetry.py` reuses
  `shared_core.telemetry.connector.trace_connector_execution` --
  Prompt 024 had already built this exact "Integrate with Prompt 024"
  hook in anticipation of this prompt, so this module is a thin wrapper
  adding only the "Status"/"Errors" span-attribute convention on top.
- **No naming collisions**, verified the same way as every prior
  prompt's `__init__.py`: unlike Prompt 026's `@cron`/`cron.py`
  collision, `decorators.py`'s `@connector` decorator has no colliding
  submodule (the package itself is `connectors`, plural; there is no
  singular `connector.py`), confirmed via `len(__all__) ==
  len(set(__all__))` plus a `hasattr` resolution check on every name
  before finalizing.
- **Middleware is generic over `OperationContext`, not tied to one
  method's signature**: `BaseConnector.execute()` returns a
  `CommandResult`, `connect()` returns `None`, `collect_inventory()`
  returns an `InventoryReport` -- a scheduler-style `ExecuteHandler`
  bound to one return type couldn't wrap all of them. `Handler[T]`/
  `Middleware[T]` (PEP 695 generic functions parameterizing a classic
  `TypeVar`-based generic alias) let the exact same chain wrap any of
  them identically.
- **`AuthorizationError` reused, not a new connector-specific
  exception**: `build_security_middleware`'s denial raises
  `shared_core.exceptions.authorization.AuthorizationError` (Prompt 015)
  rather than adding a fifteenth `connectors/exceptions.py` class --
  "an authenticated caller lacks permission" is exactly what that
  existing exception already means.
- **Bug caught while writing `CircuitBreaker` tests, in the test itself
  (not the source)**: the first draft of
  `test_circuit_breaker_half_open_failure_reopens_immediately` used
  `failure_threshold=5` but only ever called `record_failure()` once
  before trying to read `_opened_at`, which stays `None` until the
  breaker actually opens -- `breaker._opened_at - 1` raised `TypeError:
  unsupported operand type(s) for -: 'NoneType' and 'int'`. Fixed by
  opening the breaker for real first (`failure_threshold=1`), then
  raising the threshold and resetting the failure counter before the
  second failure, so the test actually isolates "HALF_OPEN reopens
  regardless of count" from "the count coincidentally hit threshold
  again."
- **A real Windows `ResourceWarning`-turned-test-failure, found and
  fixed during `discover_ports`/`discover_host` testing**: the first
  throwaway `asyncio.start_server` fixture used a no-op accept callback
  (`lambda r, w: None`), leaving the *server-side* `StreamWriter` open
  after `check_tcp_reachable` (the client side) connected and cleanly
  closed its own end. `server.close()`/`await server.wait_closed()`
  only stops new connections -- it doesn't close already-accepted ones
  -- so the leaked writer's `__del__` finalizer fired a `ResourceWarning`
  that pytest's `unraisableexception` plugin turned into a hard test
  failure. Fixed by making the accept callback actually close its side
  too (`writer.close(); await writer.wait_closed()`).
- **No circular imports**: `connectors -> monitoring` (TCP checks,
  status rollup), `connectors -> queue` (retry policy), `connectors ->
  cache` (rate limiting), `connectors -> telemetry` (root tracing),
  `connectors -> logging` (audit), and `connectors -> exceptions`
  (`ConnectorError`/`AuthorizationError`) are all safe and
  one-directional -- none of those packages depend on `connectors`.
- **No new dependencies**: every primitive this core SDK needed already
  existed in this monorepo. Provider packages (a later phase) will each
  bring their own protocol client dependency (`asyncssh`, `pywinrm`,
  `docker`, `kubernetes`, `boto3`, ...).
