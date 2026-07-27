"""Tests for :class:`app.services.dependency.PlaybookDependencyService`,
including real circular-dependency graph traversal.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DependencyType
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_dependency import PlaybookDependencyRepository
from app.services.dependency import PlaybookDependencyService
from tests.conftest import make_playbook


def _build_service(db_session: AsyncSession) -> PlaybookDependencyService:
    return PlaybookDependencyService(
        PlaybookDependencyRepository(db_session), PlaybookRepository(db_session)
    )


class TestPlaybookDependencyService:
    async def test_create_and_list_for_playbook(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        dependency = await service.create(
            playbook.id,
            dependency_type=DependencyType.PYTHON_PACKAGE,
            name="requests",
            version_constraint=">=2.0",
        )
        assert dependency.name == "requests"

        dependencies = await service.list_for_playbook(playbook.id)
        assert len(dependencies) == 1

    async def test_create_for_missing_playbook_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.create(
                uuid.uuid4(),
                dependency_type=DependencyType.ROLE,
                name="x",
                version_constraint=None,
            )

    async def test_non_playbook_dependency_never_checked_for_cycles(
        self, db_session: AsyncSession
    ) -> None:
        playbook = await make_playbook(db_session, name="self-role")
        service = _build_service(db_session)
        # A ROLE dependency literally named after its own playbook is
        # not a circular *playbook* dependency -- roles/collections/
        # packages are a different dependency graph entirely.
        dependency = await service.create(
            playbook.id,
            dependency_type=DependencyType.ROLE,
            name="self-role",
            version_constraint=None,
        )
        assert dependency.name == "self-role"

    async def test_direct_self_reference_raises_conflict(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session, name="playbook-a")
        service = _build_service(db_session)
        with pytest.raises(ConflictError, match="circular"):
            await service.create(
                playbook.id,
                dependency_type=DependencyType.PLAYBOOK,
                name="playbook-a",
                version_constraint=None,
            )

    async def test_transitive_cycle_raises_conflict(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        playbook_a = await make_playbook(db_session, organization_id=org_id, name="playbook-a")
        playbook_b = await make_playbook(db_session, organization_id=org_id, name="playbook-b")
        service = _build_service(db_session)

        # a -> b (fine)
        await service.create(
            playbook_a.id,
            dependency_type=DependencyType.PLAYBOOK,
            name="playbook-b",
            version_constraint=None,
        )
        # b -> a would close the cycle
        with pytest.raises(ConflictError, match="circular"):
            await service.create(
                playbook_b.id,
                dependency_type=DependencyType.PLAYBOOK,
                name="playbook-a",
                version_constraint=None,
            )

    async def test_non_cyclic_playbook_dependency_succeeds(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        playbook_a = await make_playbook(db_session, organization_id=org_id, name="playbook-a")
        await make_playbook(db_session, organization_id=org_id, name="playbook-c")
        service = _build_service(db_session)

        dependency = await service.create(
            playbook_a.id,
            dependency_type=DependencyType.PLAYBOOK,
            name="playbook-c",
            version_constraint=None,
        )
        assert dependency.name == "playbook-c"

    async def test_delete(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        dependency = await service.create(
            playbook.id,
            dependency_type=DependencyType.EXTERNAL_MODULE,
            name="x",
            version_constraint=None,
        )
        await service.delete(dependency.id)
        assert await service.list_for_playbook(playbook.id) == []
