"""Tests for :class:`app.services.collection.PlaybookCollectionService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_collection import PlaybookCollectionRepository
from app.services.collection import PlaybookCollectionService
from tests.conftest import make_playbook


def _build_service(db_session: AsyncSession) -> PlaybookCollectionService:
    return PlaybookCollectionService(
        PlaybookCollectionRepository(db_session), PlaybookRepository(db_session)
    )


class TestPlaybookCollectionService:
    async def test_create_and_list_for_playbook(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        collection = await service.create(
            playbook.id,
            collection_name="community.general",
            collection_version="8.0.0",
            source="galaxy",
        )
        assert collection.collection_name == "community.general"

        collections = await service.list_for_playbook(playbook.id)
        assert len(collections) == 1

    async def test_create_for_missing_playbook_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.create(
                uuid.uuid4(), collection_name="x", collection_version=None, source=None
            )

    async def test_delete(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        collection = await service.create(
            playbook.id, collection_name="x", collection_version=None, source=None
        )
        await service.delete(collection.id)
        assert await service.list_for_playbook(playbook.id) == []
