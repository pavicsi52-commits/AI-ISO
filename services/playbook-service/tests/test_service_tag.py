"""Tests for :class:`app.services.tag.PlaybookTagService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_tag import PlaybookTagRepository
from app.services.tag import PlaybookTagService
from tests.conftest import make_playbook


def _build_service(db_session: AsyncSession) -> PlaybookTagService:
    return PlaybookTagService(PlaybookTagRepository(db_session), PlaybookRepository(db_session))


class TestPlaybookTagService:
    async def test_add_and_list_for_playbook(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        tag = await service.add(playbook.id, tag="production")
        assert tag.tag == "production"

        tags = await service.list_for_playbook(playbook.id)
        assert len(tags) == 1

    async def test_add_for_missing_playbook_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.add(uuid.uuid4(), tag="x")

    async def test_add_duplicate_tag_raises_conflict(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        await service.add(playbook.id, tag="dup")
        with pytest.raises(ConflictError):
            await service.add(playbook.id, tag="dup")

    async def test_remove(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        tag = await service.add(playbook.id, tag="x")
        await service.remove(tag.id)
        assert await service.list_for_playbook(playbook.id) == []
