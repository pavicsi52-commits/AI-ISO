"""Plugin audit trail.

Per docs/029_Enterprise_Plugin_Framework.md.txt "AUDIT": Install,
Enable, Disable, Update, Uninstall, Permission Changes, Configuration
Changes, Failures, Security Events. Emitted as structured log events
via :meth:`shared_core.logging.logger.AIIOSLogger.audit` (Prompt 014)
rather than persisted to a database table -- same reasoning as every
other Prompt 018-028 framework's own audit.py.
"""

from __future__ import annotations

from shared_core.logging.logger import get_logger

logger = get_logger("shared_core.plugins.audit")


def audit_plugin_installed(plugin_id: str, *, actor_id: str | None = None) -> None:
    """Record that a plugin was installed ("Install")."""
    logger.audit("plugin.install", actor_id=actor_id, resource=plugin_id)


def audit_plugin_enabled(plugin_id: str, *, actor_id: str | None = None) -> None:
    """Record that a plugin was enabled ("Enable")."""
    logger.audit("plugin.enable", actor_id=actor_id, resource=plugin_id)


def audit_plugin_disabled(plugin_id: str, *, actor_id: str | None = None) -> None:
    """Record that a plugin was disabled ("Disable")."""
    logger.audit("plugin.disable", actor_id=actor_id, resource=plugin_id)


def audit_plugin_updated(
    plugin_id: str, *, from_version: str, to_version: str, actor_id: str | None = None
) -> None:
    """Record that a plugin was updated to a new version ("Update")."""
    logger.audit(
        "plugin.update",
        actor_id=actor_id,
        resource=plugin_id,
        from_version=from_version,
        to_version=to_version,
    )


def audit_plugin_uninstalled(plugin_id: str, *, actor_id: str | None = None) -> None:
    """Record that a plugin was uninstalled ("Uninstall")."""
    logger.audit("plugin.uninstall", actor_id=actor_id, resource=plugin_id)


def audit_permission_change(
    plugin_id: str, *, permissions: list[str], actor_id: str | None = None
) -> None:
    """Record a change to a plugin's granted permissions ("Permission Changes")."""
    logger.audit(
        "plugin.permission.change", actor_id=actor_id, resource=plugin_id, permissions=permissions
    )


def audit_configuration_change(plugin_id: str, *, actor_id: str | None = None) -> None:
    """Record a change to a plugin's runtime configuration ("Configuration Changes")."""
    logger.audit("plugin.configuration.change", actor_id=actor_id, resource=plugin_id)


def audit_plugin_failure(plugin_id: str, *, error: str, actor_id: str | None = None) -> None:
    """Record a plugin operation failure ("Failures")."""
    logger.audit("plugin.failure", actor_id=actor_id, resource=plugin_id, error=error)


def audit_security_event(plugin_id: str, *, detail: str, actor_id: str | None = None) -> None:
    """Record a plugin-related security event ("Security Events")."""
    logger.audit("plugin.security_event", actor_id=actor_id, resource=plugin_id, detail=detail)


__all__ = [
    "audit_configuration_change",
    "audit_permission_change",
    "audit_plugin_disabled",
    "audit_plugin_enabled",
    "audit_plugin_failure",
    "audit_plugin_installed",
    "audit_plugin_uninstalled",
    "audit_plugin_updated",
    "audit_security_event",
]
