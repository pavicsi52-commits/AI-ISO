"""Direct service-layer tests for ``app/services/statistics.py``'s
recompute-update branch and license-utilization math.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import add_member, make_org

from app.models.organization_license import OrganizationLicense
from app.repositories.member import OrganizationMemberRepository
from app.repositories.organization_license import OrganizationLicenseRepository
from app.repositories.statistics import OrganizationStatisticsRepository
from app.services.statistics import OrganizationStatisticsService


async def test_recompute_creates_then_updates_existing_row(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = OrganizationStatisticsService(
        OrganizationStatisticsRepository(db_session),
        OrganizationMemberRepository(db_session),
        OrganizationLicenseRepository(db_session),
    )

    first = await service.recompute(organization.id)
    assert first.user_count == 0

    await add_member(db_session, organization.id, uuid.uuid4())
    second = await service.recompute(organization.id)
    assert second.user_count == 1
    assert second.id == first.id  # same row, updated in place


async def test_license_utilization_with_no_license_is_zero(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = OrganizationStatisticsService(
        OrganizationStatisticsRepository(db_session),
        OrganizationMemberRepository(db_session),
        OrganizationLicenseRepository(db_session),
    )
    stats = await service.recompute(organization.id)
    assert stats.license_utilization_percent == 0.0


async def test_license_utilization_computed_from_seats(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    db_session.add(
        OrganizationLicense(
            organization_id=organization.id,
            license_key="KEY",
            seat_count=4,
            consumed_seats=1,
        )
    )
    await db_session.flush()

    service = OrganizationStatisticsService(
        OrganizationStatisticsRepository(db_session),
        OrganizationMemberRepository(db_session),
        OrganizationLicenseRepository(db_session),
    )
    stats = await service.recompute(organization.id)
    assert stats.license_utilization_percent == 25.0
