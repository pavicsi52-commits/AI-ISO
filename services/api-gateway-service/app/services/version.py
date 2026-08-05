"""API version management."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.models.version import ApiVersion
from app.repositories.version import ApiVersionRepository


class VersionService:
    """Versions: registration, default selection, and deprecation."""

    def __init__(self, versions: ApiVersionRepository) -> None:
        self._versions = versions

    async def register(
        self,
        organization_id: UUID,
        *,
        service_id: UUID,
        version: str,
        is_default: bool = False,
    ) -> ApiVersion:
        """Register a new version for one service.

        If *is_default*, any previously-default version for this
        service is demoted first -- exactly one version is ever default
        at a time.
        """
        if is_default:
            await self._demote_current_default(organization_id, service_id)
        return await self._versions.create(
            ApiVersion(
                organization_id=organization_id,
                service_id=service_id,
                version=version,
                is_default=is_default,
            )
        )

    async def _demote_current_default(self, organization_id: UUID, service_id: UUID) -> None:
        current = await self._versions.get_default(organization_id, service_id)
        if current is not None:
            current.is_default = False
            await self._versions.update(current)

    async def list_for_service(self, organization_id: UUID, service_id: UUID) -> list[ApiVersion]:
        """Every version registered for one service."""
        return await self._versions.list_for_service(organization_id, service_id)

    async def deprecate(
        self,
        organization_id: UUID,
        version_id: UUID,
        *,
        message: str | None = None,
        sunset_at: datetime | None = None,
    ) -> ApiVersion:
        """Mark a version deprecated, with optional guidance and a sunset date."""
        stored = await self._versions.require_by_id(version_id)
        stored.is_deprecated = True
        stored.deprecation_message = message
        stored.sunset_at = sunset_at
        return await self._versions.update(stored)


__all__ = ["VersionService"]
