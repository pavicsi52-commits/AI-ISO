"""Tests for :class:`app.services.template.PlaybookTemplateService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ContentType
from app.repositories.playbook_template import PlaybookTemplateRepository
from app.services.template import PlaybookTemplateService


def _build_service(db_session: AsyncSession) -> PlaybookTemplateService:
    return PlaybookTemplateService(PlaybookTemplateRepository(db_session))


class TestPlaybookTemplateService:
    async def test_create_and_get_by_id(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        template = await service.create(
            organization_id=uuid.uuid4(),
            template_name="deploy-app",
            description="Deploys the app",
            content_type=ContentType.ANSIBLE_PLAYBOOK,
            content="- hosts: all\n  tasks: []\n",
            variables_schema={},
        )
        fetched = await service.get_by_id(template.id)
        assert fetched.template_name == "deploy-app"

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org_filters_by_content_type(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        await service.create(
            organization_id=org_id,
            template_name="shell-tpl",
            description=None,
            content_type=ContentType.SHELL_SCRIPT,
            content="echo hi",
            variables_schema={},
        )
        await service.create(
            organization_id=org_id,
            template_name="python-tpl",
            description=None,
            content_type=ContentType.PYTHON_SCRIPT,
            content="print('hi')",
            variables_schema={},
        )
        results = await service.list_for_org(org_id, content_type=ContentType.PYTHON_SCRIPT)
        assert len(results) == 1
        assert results[0].template_name == "python-tpl"

    async def test_delete(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        template = await service.create(
            organization_id=uuid.uuid4(),
            template_name="t1",
            description=None,
            content_type=ContentType.BASH_SCRIPT,
            content="echo hi",
            variables_schema={},
        )
        await service.delete(template.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(template.id)
