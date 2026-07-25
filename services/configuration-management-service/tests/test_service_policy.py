"""Tests for :class:`app.services.policy.ConfigurationPolicyService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.database.exceptions import DuplicateRecordError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PolicyType
from app.repositories.configuration_policy import ConfigurationPolicyRepository
from app.services.policy import ConfigurationPolicyService


def build_service(db_session: AsyncSession) -> ConfigurationPolicyService:
    return ConfigurationPolicyService(ConfigurationPolicyRepository(db_session))


async def test_create_and_get(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()

    policy = await service.create(
        organization_id=org_id,
        project_id=None,
        policy_type=PolicyType.NAMING,
        name="lowercase-only",
        description="Names must be lowercase.",
        rule={"pattern": "^[a-z-]+$"},
        enforced=True,
    )

    fetched = await service.get_by_id(policy.id)
    assert fetched.name == "lowercase-only"
    assert fetched.enforced is True


async def test_create_rejects_duplicate_name(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        project_id=None,
        policy_type=PolicyType.RETENTION,
        name="dup-policy",
        description=None,
        rule={},
        enforced=True,
    )

    with pytest.raises(DuplicateRecordError):
        await service.create(
            organization_id=org_id,
            project_id=None,
            policy_type=PolicyType.RETENTION,
            name="dup-policy",
            description=None,
            rule={},
            enforced=True,
        )


async def test_list_for_org_filters_by_type(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        project_id=None,
        policy_type=PolicyType.NAMING,
        name="naming-policy",
        description=None,
        rule={},
        enforced=True,
    )
    await service.create(
        organization_id=org_id,
        project_id=None,
        policy_type=PolicyType.DEPLOYMENT,
        name="deployment-policy",
        description=None,
        rule={},
        enforced=True,
    )

    naming_only = await service.list_for_org(org_id, policy_type=PolicyType.NAMING)
    assert len(naming_only) == 1
    assert naming_only[0].name == "naming-policy"


async def test_update_and_delete(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    policy = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        policy_type=PolicyType.ENVIRONMENT,
        name="env-policy",
        description=None,
        rule={},
        enforced=True,
    )

    updated = await service.update(policy.id, description="new", rule={"a": 1}, enforced=False)
    assert updated.enforced is False

    await service.delete(policy.id)
    with pytest.raises(NotFoundError):
        await service.get_by_id(policy.id)
