"""Tests for :class:`app.services.script.PlaybookScriptService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ContentType
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_script import PlaybookScriptRepository
from app.services.script import PlaybookScriptService
from tests.conftest import make_playbook


def _build_service(db_session: AsyncSession) -> PlaybookScriptService:
    return PlaybookScriptService(
        PlaybookScriptRepository(db_session), PlaybookRepository(db_session)
    )


class TestPlaybookScriptService:
    async def test_create_and_list_for_playbook(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        script = await service.create(
            playbook.id,
            file_name="helper.py",
            script_type=ContentType.PYTHON_SCRIPT,
            content="print('helper')",
            is_entry_point=False,
        )
        assert script.file_name == "helper.py"

        scripts = await service.list_for_playbook(playbook.id)
        assert len(scripts) == 1

    async def test_create_for_missing_playbook_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.create(
                uuid.uuid4(),
                file_name="x.py",
                script_type=ContentType.PYTHON_SCRIPT,
                content="pass",
                is_entry_point=False,
            )

    async def test_delete(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        script = await service.create(
            playbook.id,
            file_name="x.py",
            script_type=ContentType.PYTHON_SCRIPT,
            content="pass",
            is_entry_point=True,
        )
        await service.delete(script.id)
        assert await service.list_for_playbook(playbook.id) == []
