"""Plugin capability grant/deny/revoke (docs/059 "PERMISSION MODEL")."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.enums import PermissionGrantStatus, PluginPermissionCategory
from app.models.permission import PluginPermissionGrant
from app.repositories.permission import PluginPermissionRepository


class PluginPermissionService:
    """Requests, grants, denies, and revokes capability grants for one
    installed plugin instance.
    """

    def __init__(self, permissions: PluginPermissionRepository) -> None:
        self._permissions = permissions

    async def request(
        self,
        organization_id: UUID,
        plugin_installation_id: UUID,
        *,
        category: PluginPermissionCategory,
        scope: str | None = None,
        justification: str | None = None,
    ) -> PluginPermissionGrant:
        """Request one capability for an installation.

        Raises:
            ValidationError: If this category was already requested for
                this installation.
        """
        existing = await self._permissions.get_for_category(plugin_installation_id, category)
        if existing is not None:
            raise ValidationError(
                f"{category.value!r} has already been requested for this installation."
            )
        return await self._permissions.create(
            PluginPermissionGrant(
                organization_id=organization_id,
                plugin_installation_id=plugin_installation_id,
                category=category,
                scope=scope,
                justification=justification,
                status=PermissionGrantStatus.PENDING,
            )
        )

    async def grant(
        self, grant_id: UUID, *, decided_by: str | None = None
    ) -> PluginPermissionGrant:
        """Grant a pending capability request."""
        grant = await self._permissions.require_by_id(grant_id)
        grant.status = PermissionGrantStatus.GRANTED
        grant.decided_by = decided_by
        grant.decided_at = datetime.now(UTC)
        return await self._permissions.update(grant)

    async def deny(self, grant_id: UUID, *, decided_by: str | None = None) -> PluginPermissionGrant:
        """Deny a pending capability request."""
        grant = await self._permissions.require_by_id(grant_id)
        grant.status = PermissionGrantStatus.DENIED
        grant.decided_by = decided_by
        grant.decided_at = datetime.now(UTC)
        return await self._permissions.update(grant)

    async def revoke(
        self, grant_id: UUID, *, decided_by: str | None = None
    ) -> PluginPermissionGrant:
        """Revoke a previously granted capability."""
        grant = await self._permissions.require_by_id(grant_id)
        grant.status = PermissionGrantStatus.REVOKED
        grant.decided_by = decided_by
        grant.decided_at = datetime.now(UTC)
        return await self._permissions.update(grant)

    async def list_for_installation(
        self, plugin_installation_id: UUID
    ) -> list[PluginPermissionGrant]:
        """Every capability grant requested for one installation."""
        return await self._permissions.list_for_installation(plugin_installation_id)

    async def granted_categories(
        self, plugin_installation_id: UUID
    ) -> frozenset[PluginPermissionCategory]:
        """Only the currently-granted capability categories, ready to build
        a :class:`app.sandbox.engine.PluginExecutionPolicy` from.
        """
        granted = await self._permissions.list_granted(plugin_installation_id)
        return frozenset(grant.category for grant in granted)


__all__ = ["PluginPermissionService"]
