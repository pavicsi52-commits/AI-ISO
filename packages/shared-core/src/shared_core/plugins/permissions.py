"""Plugin permission model.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PERMISSIONS": Filesystem,
Database, Network, Workflow, Connector, AI, Notifications, Scheduler,
Storage. "Plugins request permissions during installation." A plugin's
manifest *requests* a set of permissions (:mod:`shared_core.plugins.manifest`);
this module tracks what was actually *granted* -- installation doesn't
imply automatic approval, matching "Security Isolation": a plugin may
run with fewer permissions than it asked for, never more.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from shared_core.plugins.exceptions import PermissionDeniedError


class PluginPermission(StrEnum):
    """Every resource category docs/029 "PERMISSIONS" names."""

    FILESYSTEM = "filesystem"
    DATABASE = "database"
    NETWORK = "network"
    WORKFLOW = "workflow"
    CONNECTOR = "connector"
    AI = "ai"
    NOTIFICATIONS = "notifications"
    SCHEDULER = "scheduler"
    STORAGE = "storage"


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    """The permission set actually granted to one installed plugin."""

    plugin_id: str
    granted: frozenset[PluginPermission]
    granted_by: str | None = None
    granted_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class PermissionRegistry:
    """Tracks which permissions each installed plugin has actually been granted."""

    def __init__(self) -> None:
        self._grants: dict[str, PermissionGrant] = {}

    def grant(
        self,
        plugin_id: str,
        permissions: frozenset[PluginPermission],
        *,
        granted_by: str | None = None,
    ) -> PermissionGrant:
        """Grant *permissions* to *plugin_id*, replacing any prior grant."""
        grant = PermissionGrant(plugin_id=plugin_id, granted=permissions, granted_by=granted_by)
        self._grants[plugin_id] = grant
        return grant

    def revoke(self, plugin_id: str) -> None:
        """Revoke every permission previously granted to *plugin_id*."""
        self._grants.pop(plugin_id, None)

    def granted_permissions(self, plugin_id: str) -> frozenset[PluginPermission]:
        """Every permission currently granted to *plugin_id* (empty if none)."""
        grant = self._grants.get(plugin_id)
        return grant.granted if grant is not None else frozenset()

    def has_permission(self, plugin_id: str, permission: PluginPermission) -> bool:
        """Whether *plugin_id* currently holds *permission*."""
        return permission in self.granted_permissions(plugin_id)

    def require_permission(self, plugin_id: str, permission: PluginPermission) -> None:
        """Raise unless *plugin_id* currently holds *permission*.

        Raises:
            PermissionDeniedError: If *plugin_id* was not granted *permission*.
        """
        if not self.has_permission(plugin_id, permission):
            raise PermissionDeniedError(
                f"Plugin {plugin_id!r} does not have {permission.value!r} permission."
            )


__all__ = ["PermissionGrant", "PermissionRegistry", "PluginPermission"]
