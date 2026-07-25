"""Plugin-Framework-specific exceptions.

Each subclasses :class:`shared_core.exceptions.plugin.PluginError`
(added fresh for this prompt, same as Prompt 027's ``ConnectorError`` --
unlike ``WorkflowError``, no ``plugin.py`` domain pre-existed in
:mod:`shared_core.exceptions`) so a bare ``except PluginError`` still
catches everything raised anywhere in this framework. Not registered in
:mod:`shared_core.exceptions.constants`'s central catalog -- same
reasoning as every other Prompt 018-028 framework: that module would
need to import from here, and this module already imports from
``shared_core.exceptions.plugin``, so a back-import would cycle. Error
codes are manually kept unique in the ``AIIOS-PLUGIN-*`` range against
the base class's ``AIIOS-PLUGIN-0001``.
"""

from __future__ import annotations

from shared_core.exceptions.plugin import PluginError


class InvalidManifestError(PluginError):
    """Raised when a plugin manifest fails parsing or schema validation."""

    error_code = "AIIOS-PLUGIN-0002"
    status_code = 422
    retryable = False
    default_user_message = "The plugin manifest is invalid."


class PluginNotFoundError(PluginError):
    """Raised when a referenced plugin id isn't registered."""

    error_code = "AIIOS-PLUGIN-0003"
    status_code = 404
    retryable = False
    default_user_message = "The requested plugin does not exist."


class PluginAlreadyInstalledError(PluginError):
    """Raised when installing a plugin id/version that's already installed."""

    error_code = "AIIOS-PLUGIN-0004"
    status_code = 409
    retryable = False
    default_user_message = "That plugin is already installed."


class DependencyResolutionError(PluginError):
    """Raised when a plugin's declared dependency can't be satisfied."""

    error_code = "AIIOS-PLUGIN-0005"
    status_code = 422
    retryable = False
    default_user_message = "The plugin's dependencies could not be resolved."


class CircularDependencyError(PluginError):
    """Raised when plugin dependencies form a cycle."""

    error_code = "AIIOS-PLUGIN-0006"
    status_code = 422
    retryable = False
    default_user_message = "A circular dependency was detected between plugins."


class VersionIncompatibleError(PluginError):
    """Raised when a plugin declares incompatibility with the running framework version."""

    error_code = "AIIOS-PLUGIN-0007"
    status_code = 422
    retryable = False
    default_user_message = "That plugin is not compatible with this platform version."


class SignatureVerificationError(PluginError):
    """Raised when a plugin's digital signature is missing or does not verify."""

    error_code = "AIIOS-PLUGIN-0008"
    status_code = 403
    retryable = False
    default_user_message = "The plugin's digital signature could not be verified."


class PermissionDeniedError(PluginError):
    """Raised when a plugin attempts an operation it wasn't granted permission for."""

    error_code = "AIIOS-PLUGIN-0009"
    status_code = 403
    retryable = False
    default_user_message = "The plugin does not have permission to perform that operation."


class SandboxViolationError(PluginError):
    """Raised when a plugin attempts to exceed its sandbox policy."""

    error_code = "AIIOS-PLUGIN-0010"
    status_code = 403
    retryable = False
    default_user_message = "The plugin violated its sandbox policy."


class PluginLoadError(PluginError):
    """Raised when a plugin's entry point fails to import or instantiate."""

    error_code = "AIIOS-PLUGIN-0011"
    status_code = 500
    retryable = False
    default_user_message = "The plugin could not be loaded."


class PluginInitializationError(PluginError):
    """Raised when a plugin's ``initialize()``/``start()`` hook raises."""

    error_code = "AIIOS-PLUGIN-0012"
    status_code = 500
    retryable = True
    default_user_message = "The plugin failed to initialize."


class InvalidLifecycleTransitionError(PluginError):
    """Raised when a plugin lifecycle transition isn't allowed from the current state."""

    error_code = "AIIOS-PLUGIN-0013"
    status_code = 409
    retryable = False
    default_user_message = "That plugin lifecycle transition is not allowed."


class HookExecutionError(PluginError):
    """Raised when a registered event hook callback raises."""

    error_code = "AIIOS-PLUGIN-0014"
    status_code = 500
    retryable = True
    default_user_message = "A plugin event hook failed during execution."


class ExtensionPointNotFoundError(PluginError):
    """Raised when a referenced extension point isn't registered."""

    error_code = "AIIOS-PLUGIN-0015"
    status_code = 404
    retryable = False
    default_user_message = "The requested extension point does not exist."


class PluginExecutionTimeoutError(PluginError):
    """Raised when a plugin operation exceeds its configured execution timeout."""

    error_code = "AIIOS-PLUGIN-0016"
    status_code = 504
    retryable = True
    default_user_message = "The plugin operation exceeded its execution timeout."


__all__ = [
    "CircularDependencyError",
    "DependencyResolutionError",
    "ExtensionPointNotFoundError",
    "HookExecutionError",
    "InvalidLifecycleTransitionError",
    "InvalidManifestError",
    "PermissionDeniedError",
    "PluginAlreadyInstalledError",
    "PluginExecutionTimeoutError",
    "PluginInitializationError",
    "PluginLoadError",
    "PluginNotFoundError",
    "SandboxViolationError",
    "SignatureVerificationError",
    "VersionIncompatibleError",
]
