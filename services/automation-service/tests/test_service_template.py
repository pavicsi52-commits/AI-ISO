"""Tests for :class:`app.services.template.AutomationTemplateService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PlaybookType
from app.repositories.automation_template import AutomationTemplateRepository
from app.services.template import AutomationTemplateService


def _build_service(db_session: AsyncSession) -> AutomationTemplateService:
    return AutomationTemplateService(AutomationTemplateRepository(db_session))


class TestAutomationTemplateService:
    async def test_create_and_get_by_id(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        org_id = uuid.uuid4()
        template = await service.create(
            organization_id=org_id,
            project_id=None,
            template_name="deploy-app",
            description="Deploys the app",
            playbook_type=PlaybookType.ANSIBLE_PLAYBOOK,
            content="- hosts: all\n  tasks: []\n",
            variables_schema={"type": "object"},
        )
        fetched = await service.get_by_id(template.id)
        assert fetched.template_name == "deploy-app"

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org_filters_by_playbook_type(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        org_id = uuid.uuid4()
        await service.create(
            organization_id=org_id,
            project_id=None,
            template_name="shell-tpl",
            description=None,
            playbook_type=PlaybookType.SHELL_SCRIPT,
            content="echo hi",
            variables_schema={},
        )
        await service.create(
            organization_id=org_id,
            project_id=None,
            template_name="python-tpl",
            description=None,
            playbook_type=PlaybookType.PYTHON_SCRIPT,
            content="print('hi')",
            variables_schema={},
        )
        results = await service.list_for_org(org_id, playbook_type=PlaybookType.PYTHON_SCRIPT)
        assert len(results) == 1
        assert results[0].template_name == "python-tpl"

    async def test_delete(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        template = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            template_name="t1",
            description=None,
            playbook_type=PlaybookType.BASH,
            content="echo hi",
            variables_schema={},
        )
        await service.delete(template.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(template.id)
