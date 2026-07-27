"""Tests for :class:`app.services.label.PlaybookLabelService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_label import PlaybookLabelRepository
from app.services.label import PlaybookLabelService
from tests.conftest import make_playbook


def _build_service(db_session: AsyncSession) -> PlaybookLabelService:
    return PlaybookLabelService(PlaybookLabelRepository(db_session), PlaybookRepository(db_session))


class TestPlaybookLabelService:
    async def test_add_and_list_for_playbook(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        label = await service.add(playbook.id, key="env", value="prod")
        assert label.key == "env"
        assert label.value == "prod"

        labels = await service.list_for_playbook(playbook.id)
        assert len(labels) == 1

    async def test_add_for_missing_playbook_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.add(uuid.uuid4(), key="k", value="v")

    async def test_add_duplicate_key_raises_conflict(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        await service.add(playbook.id, key="env", value="prod")
        with pytest.raises(ConflictError):
            await service.add(playbook.id, key="env", value="staging")

    async def test_remove(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        label = await service.add(playbook.id, key="env", value="prod")
        await service.remove(label.id)
        assert await service.list_for_playbook(playbook.id) == []
