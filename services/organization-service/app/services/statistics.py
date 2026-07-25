"""Organization analytics/statistics computation.

Per docs/033 "ORGANIZATION ANALYTICS": User Count, Project Count,
Asset Count, Workflow Count, Automation Count, Validation Count,
Storage Usage, API Usage, AI Usage, License Utilization.

Only ``user_count`` (this service's own
:class:`~app.models.member.OrganizationMember` rows) and
``license_utilization_percent`` (this service's own
:class:`~app.models.organization_license.OrganizationLicense`) are
computed from real data this service owns. Every other count
(projects, assets, workflows, automation, validation, storage/API/AI
usage) belongs to services docs/033 explicitly excludes from this
prompt's scope ("DO NOT IMPLEMENT": Project Management, Inventory,
Automation, Workflow Engine, Validation) and that don't exist yet in
this build -- those fields are honestly left at ``0`` rather than
fabricated, the same honesty precedent
``services/user-management-service``'s "Virus Scan Hook" established.
Recomputing is idempotent (upserts the one row per organization), per
"PERFORMANCE": "Background Analytics".
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.organization_license import OrganizationLicense
from app.models.statistics import OrganizationStatistics
from app.repositories.member import OrganizationMemberRepository
from app.repositories.organization_license import OrganizationLicenseRepository
from app.repositories.statistics import OrganizationStatisticsRepository


class OrganizationStatisticsService:
    """Recomputes and reads an organization's usage snapshot."""

    def __init__(
        self,
        statistics: OrganizationStatisticsRepository,
        members: OrganizationMemberRepository,
        licenses: OrganizationLicenseRepository,
    ) -> None:
        self._statistics = statistics
        self._members = members
        self._licenses = licenses

    async def recompute(self, organization_id: UUID) -> OrganizationStatistics:
        """Recompute and persist *organization_id*'s usage snapshot ("Collect ...")."""
        user_count = await self._members.count_for_org(organization_id)
        license_ = await self._licenses.get_for_org(organization_id)
        utilization = _license_utilization(license_)

        existing = await self._statistics.get_for_org(organization_id)
        now = datetime.now(UTC)
        if existing is not None:
            existing.user_count = user_count
            existing.license_utilization_percent = utilization
            existing.computed_at = now
            return existing
        return await self._statistics.create(
            OrganizationStatistics(
                organization_id=organization_id,
                user_count=user_count,
                license_utilization_percent=utilization,
                computed_at=now,
            )
        )

    async def get_or_recompute(self, organization_id: UUID) -> OrganizationStatistics:
        """Return the last-computed snapshot, computing it for the first time if missing."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)


def _license_utilization(license_: OrganizationLicense | None) -> float:
    if license_ is None or license_.seat_count <= 0:
        return 0.0
    return round((license_.consumed_seats / license_.seat_count) * 100, 2)


__all__ = ["OrganizationStatisticsService"]
