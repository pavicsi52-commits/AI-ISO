"""Discovery profile management. Per docs/037 "DISCOVERY PROFILES"."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError

from app.events.discovery_events import DiscoveryProfileCreatedEvent
from app.models.discovery_profile import DiscoveryProfile
from app.models.enums import ProfileType, ProtocolType
from app.repositories.discovery_profile import DiscoveryProfileRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]
_SOURCE_SERVICE = "discovery-service"


class DiscoveryProfileService:
    """Creates, updates, and lists reusable discovery scan profiles."""

    def __init__(
        self, profiles: DiscoveryProfileRepository, publish_event: EventPublisher | None = None
    ) -> None:
        self._profiles = profiles
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, profile_id: UUID) -> DiscoveryProfile:
        """Return the profile identified by *profile_id*.

        Raises:
            NotFoundError: If no such profile exists.
        """
        return await self._profiles.require_by_id(profile_id)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryProfile]:
        """Every profile defined for *organization_id*."""
        return await self._profiles.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        description: str | None,
        profile_type: ProfileType,
        protocols: list[ProtocolType],
        default_ports: dict[str, int],
        timeout_seconds: int,
        concurrency_limit: int,
    ) -> DiscoveryProfile:
        """Create a new discovery profile.

        Raises:
            ConflictError: If *name* is already taken within *organization_id*.
        """
        if await self._profiles.get_by_name(organization_id, name) is not None:
            raise ConflictError(f"Profile {name!r} already exists in this organization.")
        profile = await self._profiles.create(
            DiscoveryProfile(
                organization_id=organization_id,
                name=name,
                description=description,
                profile_type=profile_type,
                protocols=[protocol.value for protocol in protocols],
                default_ports=default_ports,
                timeout_seconds=timeout_seconds,
                concurrency_limit=concurrency_limit,
            )
        )
        await self._publish(
            DiscoveryProfileCreatedEvent(
                source_service=_SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"profile_id": str(profile.id), "name": name},
            )
        )
        return profile

    async def update(
        self,
        profile_id: UUID,
        *,
        name: str,
        description: str | None,
        profile_type: ProfileType,
        protocols: list[ProtocolType],
        default_ports: dict[str, Any],
        timeout_seconds: int,
        concurrency_limit: int,
    ) -> DiscoveryProfile:
        """Replace a profile's mutable fields.

        Raises:
            NotFoundError: If no such profile exists.
        """
        profile = await self.get_by_id(profile_id)
        profile.name = name
        profile.description = description
        profile.profile_type = profile_type
        profile.protocols = [protocol.value for protocol in protocols]
        profile.default_ports = default_ports
        profile.timeout_seconds = timeout_seconds
        profile.concurrency_limit = concurrency_limit
        return profile

    async def delete(self, profile_id: UUID) -> None:
        """Delete a profile.

        Raises:
            NotFoundError: If no such profile exists.
        """
        await self._profiles.delete(profile_id)


__all__ = ["DiscoveryProfileService"]
