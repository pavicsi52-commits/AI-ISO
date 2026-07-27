"""Tests for :class:`app.services.variable.PlaybookVariableService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_variable import PlaybookVariableRepository
from app.services.variable import PlaybookVariableService
from tests.conftest import make_playbook


def _build_service(db_session: AsyncSession) -> PlaybookVariableService:
    return PlaybookVariableService(
        PlaybookVariableRepository(db_session), PlaybookRepository(db_session)
    )


class TestPlaybookVariableService:
    async def test_create_and_list_for_playbook(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        variable = await service.create(
            playbook.id,
            name="hostname",
            default_value=None,
            required=True,
            runtime=False,
            is_secret_reference=False,
            env_var_name="HOSTNAME",
            validation_rule=None,
            description="Target hostname",
        )
        assert variable.organization_id == playbook.organization_id

        variables = await service.list_for_playbook(playbook.id)
        assert len(variables) == 1
        assert variables[0].name == "hostname"

    async def test_create_for_missing_playbook_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.create(
                uuid.uuid4(),
                name="x",
                default_value=None,
                required=False,
                runtime=False,
                is_secret_reference=False,
                env_var_name=None,
                validation_rule=None,
                description=None,
            )

    async def test_delete(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        variable = await service.create(
            playbook.id,
            name="x",
            default_value=None,
            required=False,
            runtime=False,
            is_secret_reference=False,
            env_var_name=None,
            validation_rule=None,
            description=None,
        )
        await service.delete(variable.id)
        assert await service.list_for_playbook(playbook.id) == []
