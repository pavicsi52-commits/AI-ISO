"""Tests for :class:`app.services.checkpoint.PersistentCheckpointStore`
and :class:`~app.services.checkpoint.WorkflowCheckpointService`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from shared_core.workflow import Checkpoint, WorkflowState
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CheckpointType, WorkflowInstanceStatus
from app.models.workflow_instance import WorkflowInstance
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository
from app.services.checkpoint import PersistentCheckpointStore, WorkflowCheckpointService
from tests.conftest import build_version_service, make_definition, make_instance


class TestPersistentCheckpointStore:
    def test_save_keeps_in_memory_behavior_and_buffers(self) -> None:
        store = PersistentCheckpointStore()
        checkpoint = Checkpoint(
            execution_id="exec-1",
            state=WorkflowState.RUNNING,
            completed_node_ids=("start",),
            variables_snapshot={"x": 1},
        )
        store.save(checkpoint)

        assert store.has_checkpoint("exec-1") is True
        assert store.restore("exec-1") == checkpoint

    def test_drain_pending_returns_and_clears(self) -> None:
        store = PersistentCheckpointStore()
        checkpoint = Checkpoint(
            execution_id="exec-1",
            state=WorkflowState.RUNNING,
            completed_node_ids=(),
            variables_snapshot={},
        )
        store.save(checkpoint)

        drained = store.drain_pending()
        assert drained == [checkpoint]
        assert store.drain_pending() == []


async def _linear_instance(db_session: AsyncSession) -> WorkflowInstance:
    definition = await make_definition(db_session)
    version = await build_version_service(db_session).create_version(
        definition,
        nodes=[
            {"node_id": "start", "node_type": "start", "name": "start"},
            {"node_id": "end", "node_type": "end", "name": "end"},
        ],
        edges=[{"from_node_id": "start", "to_node_id": "end"}],
        current_version_number=None,
    )
    return await make_instance(db_session, definition, version)


class TestWorkflowCheckpointService:
    async def test_persist_translates_sdk_state_and_stores(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = WorkflowCheckpointService(WorkflowCheckpointRepository(db_session))
        checkpoint = Checkpoint(
            execution_id=str(instance.id),
            state=WorkflowState.COMPLETED,
            completed_node_ids=("start", "task", "end"),
            variables_snapshot={"x": 1},
            created_at=datetime.now(UTC),
        )
        stored = await service.persist(
            organization_id=instance.organization_id, instance_id=instance.id, checkpoint=checkpoint
        )
        assert stored.state == WorkflowInstanceStatus.COMPLETED
        assert stored.completed_node_ids == ["start", "task", "end"]
        assert stored.checkpoint_type == CheckpointType.AUTOMATIC

    async def test_list_and_get_latest_for_instance(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = WorkflowCheckpointService(WorkflowCheckpointRepository(db_session))
        first = Checkpoint(
            execution_id=str(instance.id),
            state=WorkflowState.RUNNING,
            completed_node_ids=("start",),
            variables_snapshot={},
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        second = Checkpoint(
            execution_id=str(instance.id),
            state=WorkflowState.COMPLETED,
            completed_node_ids=("start", "end"),
            variables_snapshot={},
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        await service.persist(
            organization_id=instance.organization_id, instance_id=instance.id, checkpoint=first
        )
        await service.persist(
            organization_id=instance.organization_id, instance_id=instance.id, checkpoint=second
        )

        all_checkpoints = await service.list_for_instance(instance.id)
        assert len(all_checkpoints) == 2

        latest = await service.get_latest_for_instance(instance.id)
        assert latest is not None
        assert latest.state == WorkflowInstanceStatus.COMPLETED

    async def test_get_latest_for_instance_none_when_empty(self, db_session: AsyncSession) -> None:
        service = WorkflowCheckpointService(WorkflowCheckpointRepository(db_session))
        assert await service.get_latest_for_instance(uuid.uuid4()) is None
