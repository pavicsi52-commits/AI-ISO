"""Tests for :class:`app.services.repository_folder.PlaybookRepositoryFolderService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RepositoryType, RepositoryVisibility
from app.repositories.playbook_repository import PlaybookRepositoryFolderRepository
from app.services.repository_folder import PlaybookRepositoryFolderService


def _build_service(db_session: AsyncSession) -> PlaybookRepositoryFolderService:
    return PlaybookRepositoryFolderService(PlaybookRepositoryFolderRepository(db_session))


class TestPlaybookRepositoryFolderService:
    async def test_create_and_get_by_id(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        folder = await service.create(
            organization_id=uuid.uuid4(),
            name="platform-team",
            description="Shared platform playbooks",
            repository_type=RepositoryType.SHARED,
            visibility=RepositoryVisibility.ORGANIZATION,
        )
        fetched = await service.get_by_id(folder.id)
        assert fetched.name == "platform-team"

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        await service.create(
            organization_id=org_id,
            name="f1",
            description=None,
            repository_type=RepositoryType.PROJECT,
            visibility=RepositoryVisibility.PRIVATE,
        )
        folders = await service.list_for_org(org_id)
        assert len(folders) == 1

    async def test_delete(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        folder = await service.create(
            organization_id=uuid.uuid4(),
            name="f1",
            description=None,
            repository_type=RepositoryType.PROJECT,
            visibility=RepositoryVisibility.PRIVATE,
        )
        await service.delete(folder.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(folder.id)
