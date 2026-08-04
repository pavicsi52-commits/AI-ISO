"""Recording and summarising incident impact.

Wraps ``app/impact/engine.py``. Discovering what is affected -- the
knowledge-graph traversal, the dependency walk -- is supplied by the
caller as a list of already-identified services; this service does not
own that discovery, only the assessment built from it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.impact.engine import ServiceImpact, overall_impact, risk_level_for, summarise
from app.models.enums import ImpactLevel
from app.models.impact import IncidentAssetImpact, IncidentImpact, IncidentServiceImpact
from app.repositories.impact import AssetImpactRepository, ImpactRepository, ServiceImpactRepository
from app.repositories.incident import IncidentRepository


class ImpactService:
    """Impact assessment: recording, summarising, and risk banding."""

    def __init__(
        self,
        impacts: ImpactRepository,
        service_impacts: ServiceImpactRepository,
        asset_impacts: AssetImpactRepository,
        incidents: IncidentRepository,
    ) -> None:
        self._impacts = impacts
        self._service_impacts = service_impacts
        self._asset_impacts = asset_impacts
        self._incidents = incidents

    async def assess(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        services: list[ServiceImpact],
        assets: list[tuple[str, str | None, ImpactLevel, str | None]] | None = None,
        business_impact: ImpactLevel = ImpactLevel.NONE,
        customer_impact: ImpactLevel = ImpactLevel.NONE,
        affected_users_estimate: int | None = None,
        assessed_by: str | None = None,
        now: datetime | None = None,
    ) -> IncidentImpact:
        """Record a fresh impact assessment and derive the incident's risk.

        A new row every time, never an update to the last one -- see
        ``app/models/impact.py`` for why the sequence itself is part of
        the record a review reads.
        """
        moment = now or datetime.now(UTC)
        stored = await self._incidents.require_in_org(organization_id, incident_id)

        for one in services:
            await self._service_impacts.create(
                IncidentServiceImpact(
                    organization_id=organization_id,
                    incident_id=incident_id,
                    service_name=one.service_name,
                    impact_level=one.impact_level,
                    is_root=one.is_root,
                )
            )
        for asset_id, asset_name, level, detail in assets or []:
            await self._asset_impacts.create(
                IncidentAssetImpact(
                    organization_id=organization_id,
                    incident_id=incident_id,
                    asset_id=asset_id,
                    asset_name=asset_name or asset_id,
                    impact_level=level,
                    detail=detail,
                )
            )

        worst = overall_impact(services)
        risk = risk_level_for(
            overall=worst,
            affected_service_count=len(services),
            has_customer_impact=customer_impact is not ImpactLevel.NONE,
        )

        created = await self._impacts.create(
            IncidentImpact(
                organization_id=organization_id,
                incident_id=incident_id,
                business_impact=business_impact,
                customer_impact=customer_impact,
                topology_impact=worst,
                risk_level=risk,
                affected_users_estimate=affected_users_estimate,
                assessed_by=assessed_by,
                assessed_at=moment,
            )
        )

        stored.risk_level = risk
        await self._incidents.update(stored)
        return created

    async def summary_for(self, organization_id: UUID, incident_id: UUID) -> dict[str, object]:
        """The latest assessment plus a per-band breakdown of affected services."""
        await self._incidents.require_in_org(organization_id, incident_id)
        latest = await self._impacts.latest(organization_id, incident_id)
        services = await self._service_impacts.list_for_incident(organization_id, incident_id)
        return {
            "latest": latest,
            "services": services,
            "by_level": summarise(
                [ServiceImpact(one.service_name, one.impact_level, one.is_root) for one in services]
            ),
        }

    async def history(self, organization_id: UUID, incident_id: UUID) -> list[IncidentImpact]:
        """Every assessment for one incident, newest first."""
        await self._incidents.require_in_org(organization_id, incident_id)
        return await self._impacts.list_for_incident(organization_id, incident_id)


__all__ = ["ImpactService"]
