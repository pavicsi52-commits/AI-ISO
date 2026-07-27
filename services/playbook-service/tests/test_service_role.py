"""Tests for :class:`app.services.role.PlaybookRoleService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_role import PlaybookRoleRepository
from app.services.role import PlaybookRoleService
from tests.conftest import make_playbook


def _build_service(db_session: AsyncSession) -> PlaybookRoleService:
    return PlaybookRoleService(PlaybookRoleRepository(db_session), PlaybookRepository(db_session))


class TestPlaybookRoleService:
    async def test_create_and_list_for_playbook(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        role = await service.create(
            playbook.id, role_name="geerlingguy.nginx", role_source="galaxy", role_version="3.1.0"
        )
        assert role.role_name == "geerlingguy.nginx"

        roles = await service.list_for_playbook(playbook.id)
        assert len(roles) == 1

    async def test_create_for_missing_playbook_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.create(
                uuid.uuid4(), role_name="x", role_source="galaxy", role_version=None
            )

    async def test_delete(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        role = await service.create(
            playbook.id, role_name="x", role_source="git", role_version=None
        )
        await service.delete(role.id)
        assert await service.list_for_playbook(playbook.id) == []
