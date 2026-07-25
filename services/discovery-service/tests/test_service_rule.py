"""Tests for :mod:`app.services.rule` -- :func:`matches_rule` and
:class:`DiscoveryRuleService`, against a real (SAVEPOINT-isolated)
Postgres session.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_rule import DiscoveryRule
from app.models.enums import RuleType
from app.repositories.discovery_rule import DiscoveryRuleRepository
from app.services.rule import DiscoveryRuleService, matches_rule
from tests.conftest import seed_profile


def _rule(operator: str, value: object) -> DiscoveryRule:
    return DiscoveryRule(
        organization_id=uuid.uuid4(),
        rule_type=RuleType.INCLUDE,
        field="address",
        operator=operator,
        value=value,
        priority=0,
    )


def test_matches_rule_eq() -> None:
    assert matches_rule(_rule("eq", "192.0.2.1"), "192.0.2.1") is True
    assert matches_rule(_rule("eq", "192.0.2.1"), "192.0.2.2") is False


def test_matches_rule_ne() -> None:
    assert matches_rule(_rule("ne", "192.0.2.1"), "192.0.2.2") is True
    assert matches_rule(_rule("ne", "192.0.2.1"), "192.0.2.1") is False


def test_matches_rule_contains() -> None:
    assert matches_rule(_rule("contains", "192.0.2"), "192.0.2.1") is True
    assert matches_rule(_rule("contains", "10.0.0"), "192.0.2.1") is False


def test_matches_rule_unsupported_operator_returns_false() -> None:
    assert matches_rule(_rule("regex", ".*"), "192.0.2.1") is False


def test_matches_rule_none_candidate_returns_false() -> None:
    assert matches_rule(_rule("eq", "192.0.2.1"), None) is False


def _service(session: AsyncSession) -> DiscoveryRuleService:
    return DiscoveryRuleService(DiscoveryRuleRepository(session))


async def test_create_and_list_for_org(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    rule = await service.create(
        organization_id=org_id,
        profile_id=None,
        rule_type=RuleType.EXCLUDE,
        field="address",
        operator="eq",
        value="10.0.0.1",
        priority=3,
    )
    assert rule.id is not None
    assert rule.priority == 3

    records = await service.list_for_org(org_id)
    assert {record.id for record in records} == {rule.id}


async def test_list_for_profile(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    profile = await seed_profile(db_session, organization_id=org_id)
    other_profile = await seed_profile(db_session, organization_id=org_id)

    in_profile = await service.create(
        organization_id=org_id,
        profile_id=profile.id,
        rule_type=RuleType.CLASSIFICATION,
        field="protocol",
        operator="eq",
        value="ssh",
    )
    await service.create(
        organization_id=org_id,
        profile_id=other_profile.id,
        rule_type=RuleType.CLASSIFICATION,
        field="protocol",
        operator="eq",
        value="http",
    )

    records = await service.list_for_profile(profile.id)
    assert {record.id for record in records} == {in_profile.id}


async def test_delete_removes_rule(db_session: AsyncSession) -> None:
    service = _service(db_session)
    rule = await service.create(
        organization_id=uuid.uuid4(),
        profile_id=None,
        rule_type=RuleType.INCLUDE,
        field="address",
        operator="eq",
        value="x",
    )
    await service.delete(rule.id)
    records = await service.list_for_org(rule.organization_id)
    assert records == []


async def test_delete_unknown_rule_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.delete(uuid.uuid4())
