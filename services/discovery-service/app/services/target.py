"""Discovery target management. No REST surface of its own -- docs/037's
own literal REST list never names a ``/discovery/targets`` endpoint;
target rows are created internally as a side effect of the
``/discovery/*-scan`` endpoints (see ``app/schemas/scan.py``'s own
module docstring) and re-used by ``POST /discovery/jobs``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.discovery_target import DiscoveryTarget
from app.models.enums import ProtocolType, TargetType
from app.repositories.discovery_target import DiscoveryTargetRepository


class DiscoveryTargetService:
    """Creates and lists discovery targets."""

    def __init__(self, targets: DiscoveryTargetRepository) -> None:
        self._targets = targets

    async def list_for_profile(self, profile_id: UUID) -> list[DiscoveryTarget]:
        """Every active target registered under *profile_id*."""
        return await self._targets.list_for_profile(profile_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID | None,
        target_type: TargetType,
        address: str,
        protocol: ProtocolType,
        port: int | None = None,
        credential_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DiscoveryTarget:
        """Register a new target."""
        return await self._targets.create(
            DiscoveryTarget(
                organization_id=organization_id,
                profile_id=profile_id,
                target_type=target_type,
                address=address,
                protocol=protocol,
                port=port,
                credential_id=credential_id,
                metadata_=metadata or {},
            )
        )


__all__ = ["DiscoveryTargetService"]
