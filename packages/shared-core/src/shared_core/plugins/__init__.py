"""Enterprise Plugin Framework.

Per docs/029_Enterprise_Plugin_Framework.md.txt. A secure, modular
plugin system letting functionality be added to AI-IOS without
modifying the platform core: manifests (YAML/JSON), dependency
resolution, versioning, a full install/enable/initialize/start/pause/
resume/stop/disable/update/uninstall lifecycle, permission-gated
sandboxing, event hooks, and extension points into the UI, backend,
Workflow SDK, Connector SDK, and AI framework, plus integration with
this codebase's event, telemetry, metrics, and audit frameworks
(Prompts 020, 024).

Business-specific plugin behavior is never implemented by this
framework itself, per docs/029 "DO NOT IMPLEMENT" -- a plugin author
subclasses :class:`~shared_core.plugins.sdk.base.Plugin` and this
framework handles loading, lifecycle, permissions, sandboxing, and
observability identically regardless of what that plugin actually does.
"""

from __future__ import annotations

from shared_core.plugins.ai import AiExtensions
from shared_core.plugins.audit import (
    audit_configuration_change,
    audit_permission_change,
    audit_plugin_disabled,
    audit_plugin_enabled,
    audit_plugin_failure,
    audit_plugin_installed,
    audit_plugin_uninstalled,
    audit_plugin_updated,
    audit_security_event,
)
from shared_core.plugins.backend import BackendExtensions
from shared_core.plugins.configuration import PluginConfigurationStore, validate_configuration
from shared_core.plugins.connector import ConnectorExtensions
from shared_core.plugins.constants import (
    DEFAULT_CPU_LIMIT_SECONDS,
    DEFAULT_EXECUTION_TIMEOUT_SECONDS,
    DEFAULT_HOOK_TIMEOUT_SECONDS,
    DEFAULT_INITIALIZE_TIMEOUT_SECONDS,
    DEFAULT_MAX_DEPENDENCY_DEPTH,
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_SOURCE_SERVICE,
    DEFAULT_START_TIMEOUT_SECONDS,
    DEFAULT_STOP_TIMEOUT_SECONDS,
    FRAMEWORK_VERSION,
)
from shared_core.plugins.decorators import (
    extension,
    get_extension_target,
    get_hook_name,
    hook,
    retryable,
    timed,
)
from shared_core.plugins.dependency import PluginDependency
from shared_core.plugins.events import (
    PluginDisabledEvent,
    PluginEnabledEvent,
    PluginEvent,
    PluginFailedEvent,
    PluginInstalledEvent,
    PluginStartedEvent,
    PluginStoppedEvent,
    PluginUninstalledEvent,
    PluginUpdatedEvent,
    build_plugin_event,
)
from shared_core.plugins.exceptions import (
    CircularDependencyError,
    DependencyResolutionError,
    ExtensionPointNotFoundError,
    HookExecutionError,
    InvalidLifecycleTransitionError,
    InvalidManifestError,
    PermissionDeniedError,
    PluginAlreadyInstalledError,
    PluginExecutionTimeoutError,
    PluginInitializationError,
    PluginLoadError,
    PluginNotFoundError,
    SandboxViolationError,
    SignatureVerificationError,
    VersionIncompatibleError,
)
from shared_core.plugins.extensions import (
    ExtensionContribution,
    ExtensionPoint,
    ExtensionRegistry,
    NamespacedExtensions,
)
from shared_core.plugins.factory import create_plugin_framework
from shared_core.plugins.health import (
    PluginFrameworkHealthReport,
    PluginHealthReport,
    build_framework_health_report,
    build_plugin_health_report,
)
from shared_core.plugins.helpers import manifest_summary, plugin_summary
from shared_core.plugins.hooks import (
    AFTER_STARTUP,
    AUTOMATION_FINISHED,
    BEFORE_SHUTDOWN,
    BEFORE_STARTUP,
    CONNECTOR_CONNECTED,
    NOTIFICATION_SENT,
    VALIDATION_COMPLETED,
    WORKFLOW_COMPLETED,
    WORKFLOW_STARTED,
    HookCallback,
    HookRegistration,
    HookRegistry,
)
from shared_core.plugins.installer import PluginInstaller
from shared_core.plugins.lifecycle import PluginLifecycle, PluginState
from shared_core.plugins.loader import PluginLoader, parse_entry_point
from shared_core.plugins.manager import EventHandler, PluginManager
from shared_core.plugins.manifest import (
    PluginManifest,
    manifest_to_dict,
    parse_manifest_dict,
    parse_manifest_json,
    parse_manifest_yaml,
    require_valid_signature,
    sign_manifest,
    verify_manifest_signature,
)
from shared_core.plugins.metadata import PluginMetadata, PluginType
from shared_core.plugins.metrics import (
    measure_execution,
    plugin_execution_seconds,
    plugin_extension_count,
    plugin_failures_total,
    plugin_hook_count,
    plugin_memory_usage_mb,
    plugins_installed_total,
    plugins_running_total,
    record_extension_count,
    record_failure,
    record_hook_count,
    record_installed,
    record_memory_usage,
    record_running,
)
from shared_core.plugins.middleware import (
    Handler,
    Middleware,
    PluginOperationContext,
    apply_middleware,
    audit_middleware,
    build_permission_middleware,
    build_sandbox_middleware,
    build_telemetry_middleware,
    logging_middleware,
    metrics_collection_middleware,
)
from shared_core.plugins.permissions import PermissionGrant, PermissionRegistry, PluginPermission
from shared_core.plugins.registry import PluginRecord, PluginRegistry
from shared_core.plugins.resolver import DependencyResolver
from shared_core.plugins.sandbox import PluginSandbox, SandboxPolicy
from shared_core.plugins.sdk import Plugin, PluginContext
from shared_core.plugins.storage import PluginStorage
from shared_core.plugins.telemetry import (
    trace_plugin_execution,
    trace_plugin_hook,
    trace_plugin_lifecycle,
    trace_plugin_load,
)
from shared_core.plugins.ui import UiExtensions
from shared_core.plugins.unloader import PluginUnloader
from shared_core.plugins.updater import PluginUpdater
from shared_core.plugins.validator import validate_manifest
from shared_core.plugins.versioning import (
    MigrationHook,
    MigrationRegistry,
    is_compatible,
    is_downgrade,
    is_upgrade,
    parse_version,
    require_compatible,
)
from shared_core.plugins.workflow import WorkflowExtensions

__all__ = [
    "AFTER_STARTUP",
    "AUTOMATION_FINISHED",
    "BEFORE_SHUTDOWN",
    "BEFORE_STARTUP",
    "CONNECTOR_CONNECTED",
    "DEFAULT_CPU_LIMIT_SECONDS",
    "DEFAULT_EXECUTION_TIMEOUT_SECONDS",
    "DEFAULT_HOOK_TIMEOUT_SECONDS",
    "DEFAULT_INITIALIZE_TIMEOUT_SECONDS",
    "DEFAULT_MAX_DEPENDENCY_DEPTH",
    "DEFAULT_MEMORY_LIMIT_MB",
    "DEFAULT_SOURCE_SERVICE",
    "DEFAULT_START_TIMEOUT_SECONDS",
    "DEFAULT_STOP_TIMEOUT_SECONDS",
    "FRAMEWORK_VERSION",
    "NOTIFICATION_SENT",
    "VALIDATION_COMPLETED",
    "WORKFLOW_COMPLETED",
    "WORKFLOW_STARTED",
    "AiExtensions",
    "BackendExtensions",
    "CircularDependencyError",
    "ConnectorExtensions",
    "DependencyResolutionError",
    "DependencyResolver",
    "EventHandler",
    "ExtensionContribution",
    "ExtensionPoint",
    "ExtensionPointNotFoundError",
    "ExtensionRegistry",
    "Handler",
    "HookCallback",
    "HookExecutionError",
    "HookRegistration",
    "HookRegistry",
    "InvalidLifecycleTransitionError",
    "InvalidManifestError",
    "Middleware",
    "MigrationHook",
    "MigrationRegistry",
    "NamespacedExtensions",
    "PermissionDeniedError",
    "PermissionGrant",
    "PermissionRegistry",
    "Plugin",
    "PluginAlreadyInstalledError",
    "PluginConfigurationStore",
    "PluginContext",
    "PluginDependency",
    "PluginDisabledEvent",
    "PluginEnabledEvent",
    "PluginEvent",
    "PluginExecutionTimeoutError",
    "PluginFailedEvent",
    "PluginFrameworkHealthReport",
    "PluginHealthReport",
    "PluginInitializationError",
    "PluginInstalledEvent",
    "PluginInstaller",
    "PluginLifecycle",
    "PluginLoadError",
    "PluginLoader",
    "PluginManager",
    "PluginManifest",
    "PluginMetadata",
    "PluginNotFoundError",
    "PluginOperationContext",
    "PluginPermission",
    "PluginRecord",
    "PluginRegistry",
    "PluginSandbox",
    "PluginStartedEvent",
    "PluginState",
    "PluginStoppedEvent",
    "PluginStorage",
    "PluginType",
    "PluginUninstalledEvent",
    "PluginUnloader",
    "PluginUpdatedEvent",
    "PluginUpdater",
    "SandboxPolicy",
    "SandboxViolationError",
    "SignatureVerificationError",
    "UiExtensions",
    "VersionIncompatibleError",
    "WorkflowExtensions",
    "apply_middleware",
    "audit_configuration_change",
    "audit_middleware",
    "audit_permission_change",
    "audit_plugin_disabled",
    "audit_plugin_enabled",
    "audit_plugin_failure",
    "audit_plugin_installed",
    "audit_plugin_uninstalled",
    "audit_plugin_updated",
    "audit_security_event",
    "build_framework_health_report",
    "build_permission_middleware",
    "build_plugin_event",
    "build_plugin_health_report",
    "build_sandbox_middleware",
    "build_telemetry_middleware",
    "create_plugin_framework",
    "extension",
    "get_extension_target",
    "get_hook_name",
    "hook",
    "is_compatible",
    "is_downgrade",
    "is_upgrade",
    "logging_middleware",
    "manifest_summary",
    "manifest_to_dict",
    "measure_execution",
    "metrics_collection_middleware",
    "parse_entry_point",
    "parse_manifest_dict",
    "parse_manifest_json",
    "parse_manifest_yaml",
    "parse_version",
    "plugin_execution_seconds",
    "plugin_extension_count",
    "plugin_failures_total",
    "plugin_hook_count",
    "plugin_memory_usage_mb",
    "plugin_summary",
    "plugins_installed_total",
    "plugins_running_total",
    "record_extension_count",
    "record_failure",
    "record_hook_count",
    "record_installed",
    "record_memory_usage",
    "record_running",
    "require_compatible",
    "require_valid_signature",
    "retryable",
    "sign_manifest",
    "timed",
    "trace_plugin_execution",
    "trace_plugin_hook",
    "trace_plugin_lifecycle",
    "trace_plugin_load",
    "validate_configuration",
    "validate_manifest",
    "verify_manifest_signature",
]
