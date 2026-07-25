"""Tests for :class:`app.services.baseline.ConfigurationBaselineService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import BaselineType
from app.repositories.configuration_baseline import ConfigurationBaselineRepository
from app.services.baseline import ConfigurationBaselineService
from tests.conftest import make_profile


def build_service(db_session: AsyncSession) -> ConfigurationBaselineService:
    return ConfigurationBaselineService(ConfigurationBaselineRepository(db_session))


async def test_create_and_get(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()

    baseline = await service.create(
        organization_id=org_id,
        project_id=None,
        profile_id=None,
        baseline_type=BaselineType.GOLDEN_IMAGE,
        name="rhel9-golden",
        description="Golden RHEL 9 image.",
        content={"packages": ["openssh"]},
    )

    fetched = await service.get_by_id(baseline.id)
    assert fetched.name == "rhel9-golden"
    assert fetched.baseline_version == "1.0.0"


async def test_get_by_id_raises_not_found(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_list_for_org_filters_by_type(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        project_id=None,
        profile_id=None,
        baseline_type=BaselineType.GOLDEN_IMAGE,
        name="golden",
        description=None,
        content={},
    )
    await service.create(
        organization_id=org_id,
        project_id=None,
        profile_id=None,
        baseline_type=BaselineType.SECURITY_BASELINE,
        name="security",
        description=None,
        content={},
    )

    security_only = await service.list_for_org(org_id, baseline_type=BaselineType.SECURITY_BASELINE)
    assert len(security_only) == 1
    assert security_only[0].name == "security"


async def test_list_for_profile(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    await service.create(
        organization_id=profile.organization_id,
        project_id=None,
        profile_id=profile.id,
        baseline_type=BaselineType.COMPLIANCE_BASELINE,
        name="compliance-baseline",
        description=None,
        content={},
    )

    baselines = await service.list_for_profile(profile.id)
    assert len(baselines) == 1


async def test_update_and_delete(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    baseline = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        profile_id=None,
        baseline_type=BaselineType.CUSTOM_BASELINE,
        name="custom",
        description=None,
        content={},
    )

    updated = await service.update(baseline.id, name="custom", description="new", content={"a": 1})
    assert updated.description == "new"

    await service.delete(baseline.id)
    with pytest.raises(NotFoundError):
        await service.get_by_id(baseline.id)
