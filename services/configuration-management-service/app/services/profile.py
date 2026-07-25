"""Configuration profile lifecycle: the orchestrator.

Per docs/039 "CONFIGURATION PROFILE MODEL"/"PROFILE STATUS"/"AUDIT".
Every create/update writes an immutable
:class:`~app.models.configuration_version.ConfigurationVersion`
snapshot ("Configuration History") plus an audit entry, and publishes
``ConfigurationCreated``/``ConfigurationUpdated``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from uuid import UUID

from shared_core.database.filtering import Filter
from shared_core.database.pagination import PaginatedResult
from shared_core.database.sorting import SortField
from shared_core.events.base import DomainEvent

from app.events.configuration_events import ConfigurationCreatedEvent, ConfigurationUpdatedEvent
from app.models.configuration_profile import ConfigurationProfile
from app.models.enums import ConfigurationType, EnvironmentType, ProfileStatus
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.services.audit import ConfigurationAuditService
from app.services.version import ConfigurationVersionService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class ConfigurationProfileService:
    """Creates, reads, updates, and deletes configuration profiles."""

    def __init__(
        self,
        profiles: ConfigurationProfileRepository,
        versions: ConfigurationVersionService,
        audit: ConfigurationAuditService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._profiles = profiles
        self._versions = versions
        self._audit = audit
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, profile_id: UUID) -> ConfigurationProfile:
        """Return the configuration profile identified by *profile_id*.

        Raises:
            NotFoundError: If no such profile exists.
        """
        return await self._profiles.require_by_id(profile_id)

    async def list_for_org(self, organization_id: UUID) -> list[ConfigurationProfile]:
        """Every configuration profile belonging to *organization_id*."""
        return await self._profiles.list_for_org(organization_id)

    async def search(
        self,
        *,
        query: str | None,
        filters: Sequence[Filter] | None,
        sort_fields: Sequence[SortField] | None,
        page: int | None,
        page_size: int | None,
    ) -> PaginatedResult[ConfigurationProfile]:
        """Full-text search plus filter plus sort plus pagination."""
        return await self._profiles.search_and_paginate(
            query=query, filters=filters, sort_fields=sort_fields, page=page, page_size=page_size
        )

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        profile_name: str,
        description: str | None,
        environment: EnvironmentType,
        owner_id: UUID | None,
        configuration_type: ConfigurationType,
        target_assets: list[str],
        variables: dict[str, Any],
        tags: list[str],
        metadata: dict[str, Any],
        created_by: UUID | None,
    ) -> ConfigurationProfile:
        """Define a new configuration profile ("Create")."""
        profile = await self._profiles.create(
            ConfigurationProfile(
                organization_id=organization_id,
                project_id=project_id,
                profile_name=profile_name,
                description=description,
                status=ProfileStatus.DRAFT,
                environment=environment,
                owner_id=owner_id,
                configuration_type=configuration_type,
                target_assets=target_assets,
                variables=variables,
                tags=tags,
                metadata_=metadata,
            )
        )
        await self._versions.create_snapshot(
            profile.id,
            organization_id=organization_id,
            content={"variables": variables, "target_assets": target_assets},
            change_summary="Initial profile creation.",
            changed_by=created_by,
        )
        await self._audit.record(
            profile.id,
            organization_id=organization_id,
            actor_id=created_by,
            action="create",
            after={"profile_name": profile_name},
        )
        await self._publish(
            ConfigurationCreatedEvent(
                source_service="configuration-management-service",
                payload={"profile_id": str(profile.id)},
            )
        )
        return profile

    async def update(
        self,
        profile_id: UUID,
        *,
        actor_id: UUID | None,
        profile_name: str,
        description: str | None,
        status: ProfileStatus,
        environment: EnvironmentType,
        owner_id: UUID | None,
        configuration_type: ConfigurationType,
        target_assets: list[str],
        variables: dict[str, Any],
        tags: list[str],
        metadata: dict[str, Any],
        change_summary: str | None = None,
    ) -> ConfigurationProfile:
        """Replace a configuration profile's mutable fields ("Update"),
        recording a new version snapshot and publishing
        ``ConfigurationUpdated``.
        """
        profile = await self.get_by_id(profile_id)
        before = {"variables": profile.variables, "target_assets": profile.target_assets}

        profile.profile_name = profile_name
        profile.description = description
        profile.status = status
        profile.environment = environment
        profile.owner_id = owner_id
        profile.configuration_type = configuration_type
        profile.target_assets = target_assets
        profile.variables = variables
        profile.tags = tags
        profile.metadata_ = metadata
        profile = await self._profiles.update(profile)

        await self._versions.create_snapshot(
            profile_id,
            organization_id=profile.organization_id,
            content={"variables": variables, "target_assets": target_assets},
            change_summary=change_summary,
            changed_by=actor_id,
        )
        await self._audit.record(
            profile_id,
            organization_id=profile.organization_id,
            actor_id=actor_id,
            action="update",
            before=before,
            after={"variables": variables, "target_assets": target_assets},
        )
        await self._publish(
            ConfigurationUpdatedEvent(
                source_service="configuration-management-service",
                payload={"profile_id": str(profile_id)},
            )
        )
        return profile

    async def patch(
        self, profile_id: UUID, *, actor_id: UUID | None, **fields: Any
    ) -> ConfigurationProfile:
        """Apply a partial update to a configuration profile ("Update"),
        recording a new version snapshot only when ``variables`` or
        ``target_assets`` changed.
        """
        profile = await self.get_by_id(profile_id)
        tracked_change = "variables" in fields or "target_assets" in fields
        for field, value in fields.items():
            attr = "metadata_" if field == "metadata" else field
            setattr(profile, attr, value)
        profile = await self._profiles.update(profile)

        if tracked_change:
            await self._versions.create_snapshot(
                profile_id,
                organization_id=profile.organization_id,
                content={
                    "variables": profile.variables,
                    "target_assets": profile.target_assets,
                },
                change_summary="Partial update.",
                changed_by=actor_id,
            )
            await self._publish(
                ConfigurationUpdatedEvent(
                    source_service="configuration-management-service",
                    payload={"profile_id": str(profile_id)},
                )
            )
        await self._audit.record(
            profile_id,
            organization_id=profile.organization_id,
            actor_id=actor_id,
            action="patch",
            after=fields,
        )
        return profile

    async def delete(self, profile_id: UUID, *, actor_id: UUID | None) -> None:
        """Soft-delete a configuration profile ("Delete")."""
        profile = await self.get_by_id(profile_id)
        await self._profiles.delete(profile_id)
        await self._audit.record(
            profile_id,
            organization_id=profile.organization_id,
            actor_id=actor_id,
            action="delete",
        )


__all__ = ["ConfigurationProfileService"]
