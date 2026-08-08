"""Tests for :mod:`app.services.task` and :mod:`app.services.tool`.

Both services are thin state machines over real rows, so every
transition here is asserted by re-reading the row through its own
repository after the call, and every event by the real recording
:class:`~tests.conftest.RecordingPublisher`.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError

from app.models.enums import (
    PermissionCategory,
    TaskPriority,
    TaskStatus,
    ToolKind,
)
from tests.conftest import soon, utcnow

TERMINAL_STATUSES = (
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.TIMED_OUT,
)


# ---------------------------------------------------------------------------
# TaskService.create_task
# ---------------------------------------------------------------------------


class TestCreateTask:
    async def test_defaults_produce_a_pending_normal_priority_task(
        self, task_service, organization_id
    ) -> None:
        before = utcnow()

        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={"question": "why?"}
        )

        assert task.organization_id == organization_id
        assert task.task_type == "analysis"
        assert task.payload == {"question": "why?"}
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL
        assert task.checkpoint == {}
        assert task.result is None
        assert task.retry_count == 0
        assert task.max_retries == 3
        assert task.timeout_seconds == 300.0
        assert task.agent_id is None
        assert task.parent_task_id is None
        assert task.requested_by is None
        assert task.started_at is None
        assert task.completed_at is None
        assert task.scheduled_at >= before

    async def test_every_optional_field_is_persisted(
        self, task_service, tasks_repo, make_agent, db_session, organization_id
    ) -> None:
        agent = await make_agent(slug="task-owner")
        parent = await task_service.create_task(
            organization_id=organization_id, task_type="parent", payload={}
        )
        scheduled = soon(600)

        task = await task_service.create_task(
            organization_id=organization_id,
            task_type="child",
            payload={"step": 1},
            agent_id=agent.id,
            parent_task_id=parent.id,
            priority=TaskPriority.CRITICAL,
            scheduled_at=scheduled,
            max_retries=7,
            timeout_seconds=12.5,
            requested_by="operator-1",
        )

        task_id, agent_id, parent_id = task.id, agent.id, parent.id
        db_session.expire_all()
        stored = await tasks_repo.require_in_org(organization_id, task_id)

        assert stored.agent_id == agent_id
        assert stored.parent_task_id == parent_id
        assert stored.priority == TaskPriority.CRITICAL
        assert stored.scheduled_at == scheduled
        assert stored.max_retries == 7
        assert stored.timeout_seconds == 12.5
        assert stored.requested_by == "operator-1"

    async def test_publishes_task_created(self, task_service, publisher, organization_id) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}
        )

        assert publisher.names == ["TaskCreated"]
        assert publisher.events[0].organization_id == organization_id
        assert publisher.events[0].payload == {"task_id": str(task.id), "task_type": "analysis"}

    async def test_created_task_is_visible_as_due(
        self, task_service, tasks_repo, organization_id
    ) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}
        )

        due = await tasks_repo.list_due(utcnow())

        assert task.id in [row.id for row in due]


# ---------------------------------------------------------------------------
# TaskService.assign / start
# ---------------------------------------------------------------------------


class TestAssignAndStart:
    async def test_assign_sets_agent_and_status(
        self, task_service, tasks_repo, make_agent, db_session, organization_id
    ) -> None:
        agent = await make_agent(slug="assignee")
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}
        )

        await task_service.assign(task, agent_id=agent.id)

        task_id, agent_id = task.id, agent.id
        db_session.expire_all()
        stored = await tasks_repo.require_in_org(organization_id, task_id)

        assert stored.agent_id == agent_id
        assert stored.status == TaskStatus.ASSIGNED

    async def test_assign_publishes_nothing(
        self, task_service, make_agent, publisher, organization_id
    ) -> None:
        agent = await make_agent(slug="quiet-assignee")
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}
        )

        await task_service.assign(task, agent_id=agent.id)

        assert publisher.names == ["AgentRegistered", "TaskCreated"]

    async def test_start_marks_running_and_stamps_started_at(
        self, task_service, organization_id
    ) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}
        )
        before = utcnow()

        started = await task_service.start(task)

        assert started.status == TaskStatus.RUNNING
        assert started.started_at is not None
        assert started.started_at >= before
        assert started.completed_at is None


# ---------------------------------------------------------------------------
# TaskService.complete
# ---------------------------------------------------------------------------


class TestComplete:
    async def test_records_result_and_completion_time(
        self, task_service, tasks_repo, db_session, organization_id
    ) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}
        )
        before = utcnow()

        await task_service.complete(task, result={"answer": 42})

        task_id = task.id
        db_session.expire_all()
        stored = await tasks_repo.require_in_org(organization_id, task_id)

        assert stored.status == TaskStatus.COMPLETED
        assert stored.result == {"answer": 42}
        assert stored.completed_at is not None
        assert stored.completed_at >= before
        assert stored.error is None

    async def test_publishes_task_completed(self, task_service, publisher, organization_id) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}
        )

        await task_service.complete(task, result={})

        assert publisher.names == ["TaskCreated", "TaskCompleted"]
        assert publisher.events[-1].organization_id == organization_id
        assert publisher.events[-1].payload == {"task_id": str(task.id), "status": "completed"}


# ---------------------------------------------------------------------------
# TaskService.fail -- the retry-vs-terminal branch
# ---------------------------------------------------------------------------


class TestFail:
    async def test_retries_while_attempts_remain(
        self, task_service, tasks_repo, db_session, organization_id
    ) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}, max_retries=2
        )

        await task_service.fail(task, error="transient upstream error")

        task_id = task.id
        db_session.expire_all()
        stored = await tasks_repo.require_in_org(organization_id, task_id)

        assert stored.status == TaskStatus.RETRYING
        assert stored.retry_count == 1
        assert stored.error == "transient upstream error"
        assert stored.completed_at is None

    async def test_retry_branch_publishes_nothing(
        self, task_service, publisher, organization_id
    ) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}, max_retries=2
        )

        await task_service.fail(task, error="boom")

        assert publisher.names == ["TaskCreated"]

    async def test_exhausting_retries_fails_terminally(
        self, task_service, tasks_repo, db_session, organization_id
    ) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}, max_retries=2
        )

        await task_service.fail(task, error="first")
        await task_service.fail(task, error="second")
        before = utcnow()
        await task_service.fail(task, error="final")

        task_id = task.id
        db_session.expire_all()
        stored = await tasks_repo.require_in_org(organization_id, task_id)

        assert stored.retry_count == 2
        assert stored.status == TaskStatus.FAILED
        assert stored.error == "final"
        assert stored.completed_at is not None
        assert stored.completed_at >= before

    async def test_terminal_failure_publishes_task_completed(
        self, task_service, publisher, organization_id
    ) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}, max_retries=0
        )

        await task_service.fail(task, error="unrecoverable")

        assert publisher.names == ["TaskCreated", "TaskCompleted"]
        assert publisher.events[-1].payload == {"task_id": str(task.id), "status": "failed"}

    async def test_zero_max_retries_fails_on_the_first_attempt(
        self, task_service, organization_id
    ) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}, max_retries=0
        )

        failed = await task_service.fail(task, error="unrecoverable")

        assert failed.status == TaskStatus.FAILED
        assert failed.retry_count == 0


# ---------------------------------------------------------------------------
# TaskService.cancel
# ---------------------------------------------------------------------------


class TestCancel:
    async def test_cancels_a_pending_task(
        self, task_service, tasks_repo, db_session, organization_id
    ) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}
        )
        before = utcnow()

        await task_service.cancel(task)

        task_id = task.id
        db_session.expire_all()
        stored = await tasks_repo.require_in_org(organization_id, task_id)

        assert stored.status == TaskStatus.CANCELLED
        assert stored.completed_at is not None
        assert stored.completed_at >= before

    async def test_cancels_a_running_task(self, task_service, organization_id) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}
        )
        await task_service.start(task)

        cancelled = await task_service.cancel(task)

        assert cancelled.status == TaskStatus.CANCELLED

    @pytest.mark.parametrize("terminal", TERMINAL_STATUSES)
    async def test_terminal_task_is_left_alone(
        self, task_service, tasks_repo, terminal, organization_id
    ) -> None:
        task = await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}
        )
        task.status = terminal
        await tasks_repo.update(task)

        cancelled = await task_service.cancel(task)

        assert cancelled.status == terminal
        assert cancelled.completed_at is None


# ---------------------------------------------------------------------------
# ToolService.register_tool
# ---------------------------------------------------------------------------


class TestRegisterTool:
    async def test_defaults_produce_an_enabled_general_tool(
        self, tool_service, organization_id
    ) -> None:
        tool = await tool_service.register_tool(
            organization_id=organization_id,
            tool_key="probe",
            name="Probe",
            tool_kind=ToolKind.REST,
        )

        assert tool.organization_id == organization_id
        assert tool.tool_key == "probe"
        assert tool.name == "Probe"
        assert tool.tool_kind == ToolKind.REST
        assert tool.description is None
        assert tool.category == "general"
        assert tool.parameters_schema == {"type": "object", "properties": {}}
        assert tool.required_permission == PermissionCategory.TOOL_INVOCATION
        assert tool.is_mutating is False
        assert tool.enabled is True
        assert tool.is_deprecated is False
        assert tool.metadata_ == {}
        assert tool.version_number == "1.0.0"

    async def test_every_optional_field_is_persisted(
        self, tool_service, tools_repo, db_session, organization_id
    ) -> None:
        schema = {"type": "object", "properties": {"url": {"type": "string"}}}

        tool = await tool_service.register_tool(
            organization_id=organization_id,
            tool_key="restart-host",
            name="Restart Host",
            tool_kind=ToolKind.AUTOMATION,
            description="Restarts a host.",
            category="infrastructure",
            parameters_schema=schema,
            required_permission=PermissionCategory.ADMINISTRATIVE,
            is_mutating=True,
            metadata={"job_id": "abc"},
        )

        tool_id = tool.id
        db_session.expire_all()
        stored = await tools_repo.require_in_org(organization_id, tool_id)

        assert stored.description == "Restarts a host."
        assert stored.category == "infrastructure"
        assert stored.parameters_schema == schema
        assert stored.required_permission == PermissionCategory.ADMINISTRATIVE
        assert stored.is_mutating is True
        assert stored.tool_kind == ToolKind.AUTOMATION
        assert stored.metadata_ == {"job_id": "abc"}

    async def test_duplicate_tool_key_conflicts(self, tool_service, organization_id) -> None:
        await tool_service.register_tool(
            organization_id=organization_id,
            tool_key="probe",
            name="Probe",
            tool_kind=ToolKind.REST,
        )

        with pytest.raises(ConflictError, match="'probe' is already registered"):
            await tool_service.register_tool(
                organization_id=organization_id,
                tool_key="probe",
                name="Probe Again",
                tool_kind=ToolKind.WEBHOOK,
            )

    async def test_duplicate_tool_key_writes_nothing_extra(
        self, tool_service, tools_repo, organization_id
    ) -> None:
        await tool_service.register_tool(
            organization_id=organization_id,
            tool_key="probe",
            name="Probe",
            tool_kind=ToolKind.REST,
        )

        with pytest.raises(ConflictError):
            await tool_service.register_tool(
                organization_id=organization_id,
                tool_key="probe",
                name="Probe Again",
                tool_kind=ToolKind.REST,
            )

        assert len(await tools_repo.list_for_org(organization_id)) == 1

    async def test_same_tool_key_in_another_org_is_allowed(
        self, tool_service, tools_repo, organization_id
    ) -> None:
        other_org = uuid.uuid4()

        ours = await tool_service.register_tool(
            organization_id=organization_id,
            tool_key="probe",
            name="Ours",
            tool_kind=ToolKind.REST,
        )
        theirs = await tool_service.register_tool(
            organization_id=other_org, tool_key="probe", name="Theirs", tool_kind=ToolKind.REST
        )

        assert ours.id != theirs.id
        assert len(await tools_repo.list_for_org(organization_id)) == 1
        assert len(await tools_repo.list_for_org(other_org)) == 1

    async def test_registered_tool_is_immediately_enabled_for_execution(
        self, tool_service, tools_repo, organization_id
    ) -> None:
        tool = await tool_service.register_tool(
            organization_id=organization_id,
            tool_key="probe",
            name="Probe",
            tool_kind=ToolKind.REST,
        )

        enabled = await tools_repo.list_enabled(organization_id)

        assert [row.id for row in enabled] == [tool.id]


# ---------------------------------------------------------------------------
# ToolService.set_enabled / deprecate
# ---------------------------------------------------------------------------


class TestToolTransitions:
    async def test_disabling_removes_it_from_the_enabled_set(
        self, tool_service, tools_repo, db_session, organization_id
    ) -> None:
        tool = await tool_service.register_tool(
            organization_id=organization_id,
            tool_key="probe",
            name="Probe",
            tool_kind=ToolKind.REST,
        )

        await tool_service.set_enabled(tool, enabled=False)

        tool_id = tool.id
        db_session.expire_all()
        stored = await tools_repo.require_in_org(organization_id, tool_id)

        assert stored.enabled is False
        assert await tools_repo.list_enabled(organization_id) == []

    async def test_re_enabling_restores_it(self, tool_service, tools_repo, organization_id) -> None:
        tool = await tool_service.register_tool(
            organization_id=organization_id,
            tool_key="probe",
            name="Probe",
            tool_kind=ToolKind.REST,
        )
        await tool_service.set_enabled(tool, enabled=False)

        re_enabled = await tool_service.set_enabled(tool, enabled=True)

        assert re_enabled.enabled is True
        assert [row.id for row in await tools_repo.list_enabled(organization_id)] == [tool.id]

    async def test_deprecating_keeps_it_visible_but_out_of_the_enabled_set(
        self, tool_service, tools_repo, db_session, organization_id
    ) -> None:
        tool = await tool_service.register_tool(
            organization_id=organization_id,
            tool_key="legacy",
            name="Legacy",
            tool_kind=ToolKind.REST,
        )

        deprecated = await tool_service.deprecate(tool)

        tool_id = tool.id
        db_session.expire_all()
        stored = await tools_repo.require_in_org(organization_id, tool_id)

        assert deprecated.is_deprecated is True
        assert stored.is_deprecated is True
        assert stored.enabled is True
        assert await tools_repo.list_enabled(organization_id) == []
        assert [row.id for row in await tools_repo.list_for_org(organization_id)] == [tool.id]
