"""Tests for :class:`app.services.policy.PolicyService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PolicyConditionType, PolicyEffect, PolicyStatus, SubjectType
from app.repositories.authorization_policy import AuthorizationPolicyRepository
from app.repositories.policy_assignment import PolicyAssignmentRepository
from app.repositories.policy_condition import PolicyConditionRepository
from app.services.policy import ConditionInput, PolicyService


class _Recorder:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)


def _service(db_session: AsyncSession, recorder: _Recorder | None = None) -> PolicyService:
    return PolicyService(
        AuthorizationPolicyRepository(db_session),
        PolicyConditionRepository(db_session),
        PolicyAssignmentRepository(db_session),
        publish_event=recorder,
    )


async def test_create_policy_with_conditions_and_assignment(db_session: AsyncSession) -> None:
    recorder = _Recorder()
    service = _service(db_session, recorder)

    entry = await service.create(
        name="Business Hours Only",
        code=f"biz-hours-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.ALLOW,
        resource_type=None,
        action=None,
        priority=100,
        conditions=[
            ConditionInput(
                condition_type=PolicyConditionType.TIME_BASED,
                field=None,
                operator="equals",
                value={"start_hour": 9, "end_hour": 17},
            )
        ],
        subject_type=SubjectType.GLOBAL,
        subject_id=None,
        metadata={},
    )

    assert len(entry.conditions) == 1
    assert any(e.event_name == "PolicyCreated" for e in recorder.events)


async def test_get_by_id_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)

    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_get_by_id_returns_policy_with_conditions(db_session: AsyncSession) -> None:
    service = _service(db_session)
    created = await service.create(
        name="P",
        code=f"p-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.ALLOW,
        resource_type=None,
        action=None,
        priority=100,
        conditions=[
            ConditionInput(
                condition_type=PolicyConditionType.CUSTOM, field="a", operator="equals", value=1
            )
        ],
        subject_type=SubjectType.GLOBAL,
        subject_id=None,
        metadata={},
    )

    found = await service.get_by_id(created.policy.id)

    assert found.policy.id == created.policy.id
    assert len(found.conditions) == 1


async def test_update_policy_replaces_conditions(db_session: AsyncSession) -> None:
    recorder = _Recorder()
    service = _service(db_session, recorder)
    entry = await service.create(
        name="P",
        code=f"p-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.ALLOW,
        resource_type=None,
        action=None,
        priority=100,
        conditions=[
            ConditionInput(
                condition_type=PolicyConditionType.CUSTOM, field="a", operator="equals", value=1
            )
        ],
        subject_type=SubjectType.GLOBAL,
        subject_id=None,
        metadata={},
    )

    updated = await service.update(
        entry.policy.id,
        name="P renamed",
        description="desc",
        effect=PolicyEffect.DENY,
        resource_type=None,
        action=None,
        priority=200,
        status=PolicyStatus.INACTIVE,
        conditions=[
            ConditionInput(
                condition_type=PolicyConditionType.CUSTOM, field="b", operator="equals", value=2
            ),
            ConditionInput(
                condition_type=PolicyConditionType.CUSTOM, field="c", operator="equals", value=3
            ),
        ],
        metadata={},
    )

    assert updated.policy.name == "P renamed"
    assert updated.policy.effect == PolicyEffect.DENY
    assert updated.policy.status == PolicyStatus.INACTIVE
    assert len(updated.conditions) == 2
    assert any(e.event_name == "PolicyUpdated" for e in recorder.events)


async def test_delete_policy(db_session: AsyncSession) -> None:
    recorder = _Recorder()
    service = _service(db_session, recorder)
    entry = await service.create(
        name="P",
        code=f"p-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.ALLOW,
        resource_type=None,
        action=None,
        priority=100,
        conditions=[],
        subject_type=SubjectType.GLOBAL,
        subject_id=None,
        metadata={},
    )

    await service.delete(entry.policy.id)

    with pytest.raises(NotFoundError):
        await service.get_by_id(entry.policy.id)
    assert any(e.event_name == "PolicyDeleted" for e in recorder.events)


async def test_list_active_orders_by_priority(db_session: AsyncSession) -> None:
    service = _service(db_session)
    low = await service.create(
        name="Low",
        code=f"low-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.ALLOW,
        resource_type=None,
        action=None,
        priority=10,
        conditions=[],
        subject_type=SubjectType.GLOBAL,
        subject_id=None,
        metadata={},
    )
    high = await service.create(
        name="High",
        code=f"high-{uuid.uuid4().hex[:8]}",
        description=None,
        effect=PolicyEffect.ALLOW,
        resource_type=None,
        action=None,
        priority=1000,
        conditions=[],
        subject_type=SubjectType.GLOBAL,
        subject_id=None,
        metadata={},
    )

    active = await service.list_active()
    ids_in_order = [entry.policy.id for entry in active]

    assert ids_in_order.index(high.policy.id) < ids_in_order.index(low.policy.id)
