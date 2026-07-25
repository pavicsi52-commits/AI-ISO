# Enterprise Plugin Framework

A secure, modular plugin system letting functionality be added to
AI-IOS without modifying the platform core
(docs/029_Enterprise_Plugin_Framework.md.txt "OBJECTIVE"): manifests
(YAML/JSON), dependency resolution, semantic versioning with migration
hooks, a full install/enable/initialize/start/pause/resume/stop/
disable/update/uninstall lifecycle, permission-gated sandboxing, event
hooks, extension points into the UI, backend, Workflow SDK, Connector
SDK, and AI framework, plus integration with this codebase's event,
telemetry, metrics, and audit frameworks (Prompts 020, 024).

**Scope note**: business-specific plugin behavior is never implemented
by this framework itself, per docs/029 "DO NOT IMPLEMENT". A plugin
author subclasses `Plugin` and this framework handles loading,
lifecycle, permissions, sandboxing, and observability identically
regardless of what that plugin actually does.

## Developer Guide

```python
from shared_core.plugins import (
    PluginManager, PluginManifest, PluginMetadata, PluginType, PluginPermission,
)
from shared_core.plugins.sdk import Plugin, PluginContext

class MyPlugin(Plugin):
    async def on_initialize(self, context: PluginContext) -> None:
        self.context = context

    async def on_start(self) -> None:
        self.context.logger.info("MyPlugin started.")

    async def on_stop(self) -> None:
        pass

manifest = PluginManifest(
    metadata=PluginMetadata(
        plugin_id="my-plugin", name="My Plugin", version="1.0.0", category=PluginType.AUTOMATION,
    ),
    entry_point="my_package.my_plugin:MyPlugin",
    permissions=frozenset({PluginPermission.NETWORK}),
)

manager = PluginManager()
await manager.install(manifest)
manager.enable("my-plugin")
await manager.initialize("my-plugin", configuration={"key": "value"})
await manager.start("my-plugin")
# ... later
await manager.stop("my-plugin")
manager.disable("my-plugin")
manager.uninstall("my-plugin")
```

See `examples/hello_plugin.py` (+ `hello_plugin.manifest.yaml`) for a
complete, real, loadable sample plugin, and `templates/plugin_template.py`
(+ `manifest_template.yaml`) for a copy-paste starting point.

### Lifecycle

`Discover -> Validate -> Install -> Enable -> Initialize -> Start ->
Pause/Resume -> Stop -> Disable -> Update -> Uninstall`
(`lifecycle.py`'s `PluginLifecycle` state machine enforces every legal
transition; an illegal one -- e.g. updating a still-running plugin --
raises `InvalidLifecycleTransitionError` rather than silently
succeeding).

### Hooks and extension points

```python
from shared_core.plugins.decorators import hook, extension, get_hook_name, get_extension_target
from shared_core.plugins.hooks import BEFORE_STARTUP

@hook(BEFORE_STARTUP)
async def on_before_startup(*args, **kwargs) -> None: ...

@extension("ui", "menus")
def my_menu_entry() -> dict: return {"label": "My Plugin"}

# Inside on_initialize(context): "mark now, wire later" --
context.hooks.register(get_hook_name(on_before_startup), context.plugin_id, on_before_startup)
namespace, category = get_extension_target(my_menu_entry)
context.extensions.point(f"{namespace}.{category}").contribute(context.plugin_id, "menu", my_menu_entry())
```

`PluginManager.uninstall()` automatically withdraws every hook/extension
a plugin registered, so a removed plugin never leaves stale contributions
behind.

### Permissions and sandboxing

```python
from shared_core.plugins.sandbox import SandboxPolicy
from shared_core.plugins.permissions import PluginPermission

manager.set_sandbox_policy("my-plugin", SandboxPolicy(
    allowed_permissions=frozenset({PluginPermission.NETWORK}),
    allowed_network_hosts=("api.example.com",),
    execution_timeout_seconds=30.0,
))
```

A plugin's manifest *requests* permissions; installation may grant
fewer than requested (`manager.install(manifest, granted_permissions=...)`).
`PluginContext.require_permission()` raises `SandboxViolationError` if
the plugin's own sandbox doesn't grant the permission it's trying to use.

### Dependency resolution and versioning

```python
from shared_core.plugins.resolver import DependencyResolver
from shared_core.plugins.versioning import is_compatible, MigrationRegistry

resolver = DependencyResolver(manager.registry.manifests_by_id())
resolver.validate("my-plugin")   # raises DependencyResolutionError/CircularDependencyError
order = resolver.resolve_order()  # dependencies before dependents
```

Version constraints use `packaging.specifiers.SpecifierSet` (PEP 440),
not hand-rolled semver comparison.

### Digital signatures

```python
from shared_core.security.encryption import generate_rsa_keypair
from shared_core.plugins.manifest import sign_manifest, verify_manifest_signature

private_key, public_key = generate_rsa_keypair()
signature = sign_manifest(manifest, private_key=private_key)
verify_manifest_signature(signed_manifest, public_key=public_key)  # bool
```

RSA-PSS/SHA-256 over the manifest's canonical JSON (everything except
`signature` itself), via `cryptography` directly -- the same library
and RSA keypair shape Prompt 017's security framework already uses.

## Architecture Notes

- **Sandbox is a policy-and-monitoring layer, not OS-level isolation,
  documented as such**: true code-level sandboxing of arbitrary Python
  (containers, seccomp, gVisor) is out of scope for a portable,
  in-process library -- `resource.setrlimit` isn't even available on
  Windows. `sandbox.py` implements what's honestly achievable instead:
  declared policy, permission/filesystem-glob/network-allowlist checks
  every framework touchpoint calls before acting, real execution-timeout
  enforcement (`asyncio.wait_for`), and best-effort *process-wide*
  memory monitoring via `psutil`. CPU limits stay a declared, advisory
  field only. This mirrors the same honesty this codebase already
  applies to expression sandboxing (`shared_core.workflow.expressions`
  sandboxes *expressions*, never arbitrary code).
- **New `PluginError` exception domain added to `shared_core.exceptions`
  itself**, not just this package: unlike `WorkflowError` (pre-seeded),
  no `plugin.py` domain existed yet -- added `PluginError`
  (`AIIOS-PLUGIN-0001`) and registered it in both
  `exceptions/__init__.py` and `exceptions/constants.py`'s catalog. This
  package's own 15 more-specific exceptions stay out of the catalog
  (avoids a back-import cycle), matching every prior prompt's own
  `exceptions.py`.
- **New `EventType.PLUGIN` added to `shared_core.events`' shared enum**:
  unlike `EventType.WORKFLOW` (pre-built), no plugin category existed.
- **`PluginContext` carries the host's shared `HookRegistry`/
  `ExtensionRegistry` directly**: the "wire later" half of
  `@hook`/`@extension`'s "mark now, wire later" pattern -- a plugin's
  own `on_initialize` registers its tagged callbacks/contributions
  through `context.hooks`/`context.extensions` explicitly, the same
  "caller manually wires a tagged handler" model as
  `shared_core.workflow.decorators`'s `@node_handler`.
  `PluginManager.uninstall()` withdraws everything a plugin registered
  via `ExtensionRegistry.withdraw_all_from`/`HookRegistry.unregister_all_from`.
- **Five extension-point files (`ui.py`/`backend.py`/`workflow.py`/
  `connector.py`/`ai.py`) share one mechanism**: each is a thin
  `NamespacedExtensions` subclass fixing a namespace prefix over the
  same `ExtensionRegistry`/`ExtensionPoint` pair in `extensions.py` --
  avoids five near-identical reimplementations of contribute/get/list.
- **`on_initialize()`/`on_start()` failures wrap into
  `PluginInitializationError`**: caught in code review before finalizing
  -- the exception existed with a docstring promising this, but nothing
  actually raised it; `PluginManager.initialize()`/`start()` now catch
  and wrap, matching `TaskExecutionError`'s handler-wrapping precedent
  in `shared_core.workflow.executor`.
- **Reuses four existing frameworks rather than reimplementing any of
  them**: `telemetry.py` reuses `shared_core.telemetry.plugin
  .trace_plugin_execution` -- Prompt 024 had already built this exact
  "Plugin Execution" span type in anticipation of this prompt;
  `storage.py` reuses `shared_core.storage.wrapper.StorageWrapper`
  (Prompt 012), scoping every key under `plugins/<plugin_id>/`;
  `health.py` reuses `shared_core.monitoring.status.calculate_status`
  (Prompt 023); `manifest.py`'s signing reuses `cryptography` directly,
  the same RSA keypair shape as `shared_core.security.encryption
  .generate_rsa_keypair` (Prompt 017).
- **One new dependency**: `packaging` (PEP 440 version parsing/
  specifier matching) -- already present transitively, made a direct,
  pinned dependency rather than hand-rolling semver comparison.
- **No naming collisions, no circular imports**: verified via
  `len(__all__) == len(set(__all__))` across all 41 submodules plus a
  `hasattr` resolution check. `plugins -> connectors`? No -- unlike
  workflow, this framework doesn't reuse `CircuitBreaker`/retry from
  connectors; its own `decorators.py` reuses `shared_core.queue.retry
  .RetryPolicy` directly instead. `plugins -> storage`/`security`/
  `telemetry`/`monitoring`/`metrics`/`logging`/`events`/`exceptions` are
  all safe and one-directional.
