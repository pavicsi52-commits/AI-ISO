"""Tests for :class:`app.services.version.WorkflowVersionService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.workflow import InvalidWorkflowDefinitionError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import build_version_service, linear_nodes_and_edges, make_definition


class TestWorkflowVersionService:
    async def test_create_version_starts_at_initial_and_bumps_patch(
        self, db_session: AsyncSession
    ) -> None:
        nodes, edges = linear_nodes_and_edges()
        definition = await make_definition(db_session)
        service = build_version_service(db_session)

        first = await service.create_version(
            definition, nodes=nodes, edges=edges, current_version_number=None
        )
        assert first.version_number == "1.0.0"
        assert first.compiled_execution_plan == [["start"], ["task"], ["end"]]

        second = await service.create_version(
            definition, nodes=nodes, edges=edges, current_version_number="1.0.0"
        )
        assert second.version_number == "1.0.1"

    async def test_create_version_invalid_dag_raises(self, db_session: AsyncSession) -> None:
        definition = await make_definition(db_session)
        service = build_version_service(db_session)
        with pytest.raises(InvalidWorkflowDefinitionError):
            await service.create_version(
                definition,
                nodes=[{"node_id": "a", "node_type": "task", "name": "a"}],
                edges=[],
                current_version_number=None,
            )

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = build_version_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_definition_newest_first(self, db_session: AsyncSession) -> None:
        nodes, edges = linear_nodes_and_edges()
        definition = await make_definition(db_session)
        service = build_version_service(db_session)
        await service.create_version(
            definition, nodes=nodes, edges=edges, current_version_number=None
        )
        await service.create_version(
            definition, nodes=nodes, edges=edges, current_version_number="1.0.0"
        )
        versions = await service.list_for_definition(definition.id)
        assert [v.version_number for v in versions] == ["1.0.1", "1.0.0"]

    async def test_get_latest_for_definition_none_when_empty(
        self, db_session: AsyncSession
    ) -> None:
        definition = await make_definition(db_session)
        service = build_version_service(db_session)
        assert await service.get_latest_for_definition(definition.id) is None
