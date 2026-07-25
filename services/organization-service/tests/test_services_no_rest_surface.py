"""Direct service-layer tests for organization sub-resources docs/033 never
names a REST endpoint for: business units, subscriptions, resource
limits, preferences, custom metadata, tags, and domains. Each of these
services exists for programmatic completeness only (see each module's
own docstring), so they're exercised directly against the repository
layer rather than through HTTP.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import make_org

from app.models.enums import SubscriptionPlan, SubscriptionStatus
from app.repositories.activity import OrganizationActivityRepository
from app.repositories.business_unit import BusinessUnitRepository
from app.repositories.organization_domain import OrganizationDomainRepository
from app.repositories.organization_limits import OrganizationLimitsRepository
from app.repositories.organization_metadata import OrganizationMetadataRepository
from app.repositories.organization_preferences import OrganizationPreferencesRepository
from app.repositories.organization_subscription import OrganizationSubscriptionRepository
from app.repositories.tag import OrganizationTagRepository
from app.services.activity import OrganizationActivityService
from app.services.business_unit import BusinessUnitService
from app.services.domain import OrganizationDomainService
from app.services.limits import OrganizationLimitsService
from app.services.metadata import OrganizationMetadataService
from app.services.preferences import OrganizationPreferencesService
from app.services.subscription import OrganizationSubscriptionService
from app.services.tag import OrganizationTagService


async def test_business_unit_crud(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = BusinessUnitService(BusinessUnitRepository(db_session))

    parent = await service.create(
        organization.id,
        name="Corporate",
        code="CORP",
        description=None,
        parent_business_unit_id=None,
        owner_id=None,
        metadata={},
    )
    child = await service.create(
        organization.id,
        name="Regional",
        code="REG",
        description="A region",
        parent_business_unit_id=parent.id,
        owner_id=uuid.uuid4(),
        metadata={"region": "eu"},
    )
    assert child.parent_business_unit_id == parent.id

    listing = await service.list_for_org(organization.id)
    assert {u.id for u in listing} == {parent.id, child.id}

    fetched = await service.get_by_id(parent.id)
    assert fetched.name == "Corporate"

    await service.delete(child.id)
    assert {u.id for u in await service.list_for_org(organization.id)} == {parent.id}


async def test_business_unit_create_with_missing_parent_raises(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = BusinessUnitService(BusinessUnitRepository(db_session))

    with pytest.raises(NotFoundError):
        await service.create(
            organization.id,
            name="Orphan",
            code="ORPH",
            description=None,
            parent_business_unit_id=uuid.uuid4(),
            owner_id=None,
            metadata={},
        )


async def test_business_unit_get_by_id_not_found(db_session: AsyncSession) -> None:
    service = BusinessUnitService(BusinessUnitRepository(db_session))
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_subscription_get_or_create_defaults_then_change_plan(
    db_session: AsyncSession,
) -> None:
    organization = await make_org(db_session)
    activity = OrganizationActivityService(OrganizationActivityRepository(db_session))
    service = OrganizationSubscriptionService(
        OrganizationSubscriptionRepository(db_session), activity
    )

    created = await service.get_or_create(organization.id)
    assert created.plan == SubscriptionPlan.TRIAL

    changed = await service.change_plan(
        organization.id,
        plan=SubscriptionPlan.ENTERPRISE,
        status=SubscriptionStatus.ACTIVE,
        billing_reference="INV-001",
        renews_at=None,
        expires_at=None,
    )
    assert changed.plan == SubscriptionPlan.ENTERPRISE
    assert changed.billing_reference == "INV-001"

    fetched_again = await service.get_or_create(organization.id)
    assert fetched_again.plan == SubscriptionPlan.ENTERPRISE


async def test_limits_get_or_create_defaults_then_update(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = OrganizationLimitsService(OrganizationLimitsRepository(db_session))

    defaults = await service.get_or_create(organization.id)
    assert defaults.cpu_cores > 0

    updated = await service.update(
        organization.id,
        cpu_cores=32,
        memory_mb=65536,
        storage_gb=1000,
        queue_usage=100,
        concurrent_workflows=50,
        concurrent_jobs=100,
        concurrent_ai_tasks=25,
        concurrent_users=500,
        bandwidth_mbps=1000,
    )
    assert updated.cpu_cores == 32
    assert updated.bandwidth_mbps == 1000


async def test_preferences_get_or_create_defaults_then_update(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = OrganizationPreferencesService(OrganizationPreferencesRepository(db_session))

    defaults = await service.get_or_create(organization.id)
    assert defaults.organization_id == organization.id

    updated = await service.update(
        organization.id,
        dashboard_layout={"widgets": ["usage"]},
        notification_preferences={"email": True},
        ui_preferences={"density": "compact"},
    )
    assert updated.dashboard_layout == {"widgets": ["usage"]}
    assert updated.ui_preferences == {"density": "compact"}


async def test_metadata_set_list_and_remove(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = OrganizationMetadataService(OrganizationMetadataRepository(db_session))

    created = await service.set(organization.id, "cost_center", "CC-42")
    assert created.value == "CC-42"

    overwritten = await service.set(organization.id, "cost_center", "CC-99")
    assert overwritten.value == "CC-99"
    assert overwritten.id == created.id

    listing = await service.list_for_org(organization.id)
    assert len(listing) == 1

    await service.remove(organization.id, "cost_center")
    assert await service.list_for_org(organization.id) == []

    # Removing a key that no longer exists is a no-op, not an error.
    await service.remove(organization.id, "cost_center")


async def test_tag_assign_list_and_remove(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = OrganizationTagService(OrganizationTagRepository(db_session))

    tag = await service.assign(organization.id, label="pilot-customer", category="lifecycle")
    listing = await service.list_for_org(organization.id)
    assert [t.id for t in listing] == [tag.id]

    with pytest.raises(ConflictError):
        await service.assign(organization.id, label="pilot-customer", category=None)

    await service.remove(organization.id, tag.id)
    assert await service.list_for_org(organization.id) == []


async def test_tag_remove_wrong_org_not_found(db_session: AsyncSession) -> None:
    org_a = await make_org(db_session)
    org_b = await make_org(db_session)
    service = OrganizationTagService(OrganizationTagRepository(db_session))
    tag = await service.assign(org_a.id, label="beta", category=None)

    with pytest.raises(NotFoundError):
        await service.remove(org_b.id, tag.id)


async def test_tag_remove_unknown_id_not_found(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = OrganizationTagService(OrganizationTagRepository(db_session))
    with pytest.raises(NotFoundError):
        await service.remove(organization.id, uuid.uuid4())


async def test_domain_claim_list_and_remove(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = OrganizationDomainService(OrganizationDomainRepository(db_session))

    domain = await service.claim(organization.id, domain="acme.example.com", is_primary=True)
    listing = await service.list_for_org(organization.id)
    assert [d.id for d in listing] == [domain.id]

    with pytest.raises(ConflictError):
        await service.claim(organization.id, domain="acme.example.com", is_primary=False)

    await service.remove(organization.id, domain.id)
    assert await service.list_for_org(organization.id) == []


async def test_domain_remove_wrong_org_not_found(db_session: AsyncSession) -> None:
    org_a = await make_org(db_session)
    org_b = await make_org(db_session)
    service = OrganizationDomainService(OrganizationDomainRepository(db_session))
    domain = await service.claim(org_a.id, domain="beta.example.com", is_primary=False)

    with pytest.raises(NotFoundError):
        await service.remove(org_b.id, domain.id)


async def test_domain_remove_unknown_id_not_found(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = OrganizationDomainService(OrganizationDomainRepository(db_session))
    with pytest.raises(NotFoundError):
        await service.remove(organization.id, uuid.uuid4())
