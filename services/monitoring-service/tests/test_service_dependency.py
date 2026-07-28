"""Tests for :class:`app.services.dependency.MonitoringDependencyService`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DependencyType
from app.repositories.monitoring_dependency import MonitoringDependencyRepository
from app.services.dependency import MonitoringDependencyService
from tests.conftest import make_target


def _service(db_session: AsyncSession) -> MonitoringDependencyService:
    return MonitoringDependencyService(MonitoringDependencyRepository(db_session))


class TestMonitoringDependencyService:
    async def test_create_and_list_children(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        parent = await make_target(db_session)
        child = await make_target(db_session, organization_id=parent.organization_id)
        await service.create(
            organization_id=parent.organization_id,
            parent_target_id=parent.id,
            child_target_id=child.id,
            dependency_type=DependencyType.SERVICE,
        )
        children = await service.list_children(parent.id)
        assert len(children) == 1
        assert children[0].child_target_id == child.id

    async def test_list_parents(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        parent = await make_target(db_session)
        child = await make_target(db_session, organization_id=parent.organization_id)
        await service.create(
            organization_id=parent.organization_id,
            parent_target_id=parent.id,
            child_target_id=child.id,
            dependency_type=DependencyType.INFRASTRUCTURE,
        )
        parents = await service.list_parents(child.id)
        assert len(parents) == 1
        assert parents[0].parent_target_id == parent.id
