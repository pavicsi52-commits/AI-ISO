"""Repository tests for :mod:`app.repositories.task` and
:mod:`app.repositories.workflow`.

Covers :class:`AgentTaskRepository` and :class:`AgentWorkflowRepository`
against real seeded Postgres rows.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.agent import Agent
from app.models.enums import (
    AgentLifecycleStatus,
    AgentType,
    OrchestrationPattern,
    TaskPriority,
    TaskStatus,
    WorkflowRunStatus,
)
from app.models.task import AgentTask
from app.models.workflow import AgentWorkflow
from app.repositories.agent import AgentRepository
from app.repositories.task import AgentTaskRepository
from app.repositories.workflow import AgentWorkflowRepository
from tests.conftest import ago, soon, utcnow


async def _agent(
    agents_repo: AgentRepository, organization_id: uuid.UUID, *, slug: str = "agent"
) -> Agent:
    return await agents_repo.create(
        Agent(
            organization_id=organization_id,
            slug=slug,
            name=f"Agent {slug}",
            agent_type=AgentType.EXECUTOR,
            status=AgentLifecycleStatus.ACTIVE,
        )
    )


def _task(
    organization_id: uuid.UUID,
    *,
    agent_id: uuid.UUID | None = None,
    parent_task_id: uuid.UUID | None = None,
    task_type: str = "generic",
    status: TaskStatus = TaskStatus.PENDING,
    priority: TaskPriority = TaskPriority.NORMAL,
    scheduled_at,
    created_at=None,
) -> AgentTask:
    kwargs: dict[str, object] = {
        "organization_id": organization_id,
        "agent_id": agent_id,
        "parent_task_id": parent_task_id,
        "task_type": task_type,
        "status": status,
        "priority": priority,
        "scheduled_at": scheduled_at,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return AgentTask(**kwargs)


def _workflow(
    organization_id: uuid.UUID,
    *,
    agent_id: uuid.UUID | None = None,
    status: WorkflowRunStatus = WorkflowRunStatus.PENDING,
    started_at=None,
    created_at=None,
) -> AgentWorkflow:
    kwargs: dict[str, object] = {
        "organization_id": organization_id,
        "agent_id": agent_id,
        "status": status,
        "started_at": started_at,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return AgentWorkflow(**kwargs)


# ---- AgentTaskRepository.require_in_org --------------------------------------


async def test_task_require_in_org_returns_task(tasks_repo: AgentTaskRepository, organization_id):
    task = await tasks_repo.create(_task(organization_id, scheduled_at=utcnow()))

    found = await tasks_repo.require_in_org(organization_id, task.id)

    assert found.id == task.id


async def test_task_require_in_org_raises_for_other_org(
    tasks_repo: AgentTaskRepository, organization_id
):
    task = await tasks_repo.create(_task(organization_id, scheduled_at=utcnow()))

    with pytest.raises(NotFoundError):
        await tasks_repo.require_in_org(uuid.uuid4(), task.id)


async def test_task_require_in_org_raises_for_unknown_id(
    tasks_repo: AgentTaskRepository, organization_id
):
    with pytest.raises(NotFoundError):
        await tasks_repo.require_in_org(organization_id, uuid.uuid4())


# ---- AgentTaskRepository.list_due ---------------------------------------------


async def test_list_due_returns_only_due_pending_or_queued(
    tasks_repo: AgentTaskRepository, organization_id
):
    moment = utcnow()
    due_pending = await tasks_repo.create(
        _task(organization_id, status=TaskStatus.PENDING, scheduled_at=ago(60))
    )
    due_queued = await tasks_repo.create(
        _task(organization_id, status=TaskStatus.QUEUED, scheduled_at=ago(30))
    )
    await tasks_repo.create(
        _task(organization_id, status=TaskStatus.PENDING, scheduled_at=soon(3600))
    )
    await tasks_repo.create(_task(organization_id, status=TaskStatus.RUNNING, scheduled_at=ago(60)))
    await tasks_repo.create(
        _task(organization_id, status=TaskStatus.COMPLETED, scheduled_at=ago(60))
    )

    found = await tasks_repo.list_due(moment)

    assert {t.id for t in found} == {due_pending.id, due_queued.id}


async def test_list_due_includes_exact_cutoff(tasks_repo: AgentTaskRepository, organization_id):
    moment = utcnow()
    task = await tasks_repo.create(
        _task(organization_id, status=TaskStatus.PENDING, scheduled_at=moment)
    )

    found = await tasks_repo.list_due(moment)

    assert task.id in {t.id for t in found}


async def test_list_due_orders_oldest_first(tasks_repo: AgentTaskRepository, organization_id):
    moment = utcnow()
    newer = await tasks_repo.create(
        _task(organization_id, status=TaskStatus.PENDING, scheduled_at=ago(10))
    )
    older = await tasks_repo.create(
        _task(organization_id, status=TaskStatus.PENDING, scheduled_at=ago(3600))
    )

    found = await tasks_repo.list_due(moment)

    assert [t.id for t in found] == [older.id, newer.id]


async def test_list_due_respects_limit(tasks_repo: AgentTaskRepository, organization_id):
    moment = utcnow()
    await tasks_repo.create(_task(organization_id, status=TaskStatus.PENDING, scheduled_at=ago(10)))
    await tasks_repo.create(_task(organization_id, status=TaskStatus.PENDING, scheduled_at=ago(20)))

    found = await tasks_repo.list_due(moment, limit=1)

    assert len(found) == 1


async def test_list_due_empty_when_none_due(tasks_repo: AgentTaskRepository, organization_id):
    await tasks_repo.create(
        _task(organization_id, status=TaskStatus.PENDING, scheduled_at=soon(3600))
    )

    assert await tasks_repo.list_due(utcnow()) == []


# ---- AgentTaskRepository.list_children -----------------------------------------


async def test_list_children_returns_only_children_of_parent(
    tasks_repo: AgentTaskRepository, organization_id
):
    parent = await tasks_repo.create(_task(organization_id, scheduled_at=utcnow()))
    other_parent = await tasks_repo.create(_task(organization_id, scheduled_at=utcnow()))
    child = await tasks_repo.create(
        _task(organization_id, parent_task_id=parent.id, scheduled_at=utcnow())
    )
    await tasks_repo.create(
        _task(organization_id, parent_task_id=other_parent.id, scheduled_at=utcnow())
    )

    found = await tasks_repo.list_children(parent.id)

    assert [t.id for t in found] == [child.id]


async def test_list_children_empty_when_none(tasks_repo: AgentTaskRepository, organization_id):
    assert await tasks_repo.list_children(uuid.uuid4()) == []


# ---- AgentTaskRepository.list_for_agent -----------------------------------------


async def test_list_for_agent_orders_newest_first(
    tasks_repo: AgentTaskRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    older = await tasks_repo.create(
        _task(organization_id, agent_id=agent.id, scheduled_at=utcnow(), created_at=ago(3600))
    )
    newer = await tasks_repo.create(
        _task(organization_id, agent_id=agent.id, scheduled_at=utcnow(), created_at=soon(3600))
    )

    found = await tasks_repo.list_for_agent(agent.id)

    assert [t.id for t in found] == [newer.id, older.id]


async def test_list_for_agent_scoped_to_agent(
    tasks_repo: AgentTaskRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    other_agent = await _agent(agents_repo, organization_id, slug="beta")
    await tasks_repo.create(_task(organization_id, agent_id=other_agent.id, scheduled_at=utcnow()))

    assert await tasks_repo.list_for_agent(agent.id) == []


# ---- AgentTaskRepository.list_in_window -----------------------------------------


async def test_list_in_window_boundaries(tasks_repo: AgentTaskRepository, organization_id):
    since = ago(3600)
    until = soon(0)
    inside_lower = await tasks_repo.create(
        _task(organization_id, scheduled_at=utcnow(), created_at=since)
    )
    inside = await tasks_repo.create(
        _task(organization_id, scheduled_at=utcnow(), created_at=ago(1800))
    )
    at_upper_excluded = await tasks_repo.create(
        _task(organization_id, scheduled_at=utcnow(), created_at=until)
    )
    before = await tasks_repo.create(
        _task(organization_id, scheduled_at=utcnow(), created_at=ago(7200))
    )

    found = await tasks_repo.list_in_window(organization_id, since=since, until=until)

    found_ids = {t.id for t in found}
    assert found_ids == {inside_lower.id, inside.id}
    assert at_upper_excluded.id not in found_ids
    assert before.id not in found_ids


async def test_list_in_window_scoped_to_org(tasks_repo: AgentTaskRepository, organization_id):
    other_org = uuid.uuid4()
    await tasks_repo.create(_task(other_org, scheduled_at=utcnow(), created_at=ago(60)))

    found = await tasks_repo.list_in_window(organization_id, since=ago(3600), until=soon(3600))

    assert found == []


# ---- AgentTaskRepository.list_for_org -------------------------------------------


async def test_list_for_org_filters_by_status(tasks_repo: AgentTaskRepository, organization_id):
    pending = await tasks_repo.create(
        _task(organization_id, status=TaskStatus.PENDING, scheduled_at=utcnow())
    )
    await tasks_repo.create(
        _task(organization_id, status=TaskStatus.COMPLETED, scheduled_at=utcnow())
    )

    found = await tasks_repo.list_for_org(organization_id, status=TaskStatus.PENDING)

    assert [t.id for t in found] == [pending.id]
    assert found[0].status == TaskStatus.PENDING


async def test_list_for_org_pagination(tasks_repo: AgentTaskRepository, organization_id):
    first = await tasks_repo.create(
        _task(organization_id, scheduled_at=utcnow(), created_at=ago(30))
    )
    second = await tasks_repo.create(
        _task(organization_id, scheduled_at=utcnow(), created_at=ago(20))
    )
    third = await tasks_repo.create(
        _task(organization_id, scheduled_at=utcnow(), created_at=ago(10))
    )

    page1 = await tasks_repo.list_for_org(organization_id, limit=2, offset=0)
    page2 = await tasks_repo.list_for_org(organization_id, limit=2, offset=2)

    assert [t.id for t in page1] == [third.id, second.id]
    assert [t.id for t in page2] == [first.id]


async def test_list_for_org_scoped_to_org(tasks_repo: AgentTaskRepository, organization_id):
    other_org = uuid.uuid4()
    await tasks_repo.create(_task(other_org, scheduled_at=utcnow()))

    assert await tasks_repo.list_for_org(organization_id) == []


# ---- AgentWorkflowRepository.require_in_org -------------------------------------


async def test_workflow_require_in_org_returns_workflow(
    workflows_repo: AgentWorkflowRepository, organization_id
):
    workflow = await workflows_repo.create(_workflow(organization_id))

    found = await workflows_repo.require_in_org(organization_id, workflow.id)

    assert found.id == workflow.id


async def test_workflow_require_in_org_raises_for_other_org(
    workflows_repo: AgentWorkflowRepository, organization_id
):
    workflow = await workflows_repo.create(_workflow(organization_id))

    with pytest.raises(NotFoundError):
        await workflows_repo.require_in_org(uuid.uuid4(), workflow.id)


async def test_workflow_require_in_org_raises_for_unknown_id(
    workflows_repo: AgentWorkflowRepository, organization_id
):
    with pytest.raises(NotFoundError):
        await workflows_repo.require_in_org(organization_id, uuid.uuid4())


# ---- AgentWorkflowRepository.list_for_agent --------------------------------------


async def test_workflow_list_for_agent_orders_newest_first(
    workflows_repo: AgentWorkflowRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    older = await workflows_repo.create(
        _workflow(organization_id, agent_id=agent.id, created_at=ago(3600))
    )
    newer = await workflows_repo.create(
        _workflow(organization_id, agent_id=agent.id, created_at=soon(3600))
    )

    found = await workflows_repo.list_for_agent(agent.id)

    assert [w.id for w in found] == [newer.id, older.id]


async def test_workflow_list_for_agent_scoped_to_agent(
    workflows_repo: AgentWorkflowRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    other_agent = await _agent(agents_repo, organization_id, slug="beta")
    await workflows_repo.create(_workflow(organization_id, agent_id=other_agent.id))

    assert await workflows_repo.list_for_agent(agent.id) == []


# ---- AgentWorkflowRepository.list_stuck_running -----------------------------------


async def test_list_stuck_running_returns_only_old_running(
    workflows_repo: AgentWorkflowRepository, organization_id
):
    cutoff = utcnow()
    stuck = await workflows_repo.create(
        _workflow(organization_id, status=WorkflowRunStatus.RUNNING, started_at=ago(3600))
    )
    await workflows_repo.create(
        _workflow(organization_id, status=WorkflowRunStatus.RUNNING, started_at=soon(3600))
    )
    await workflows_repo.create(
        _workflow(organization_id, status=WorkflowRunStatus.RUNNING, started_at=None)
    )
    await workflows_repo.create(
        _workflow(organization_id, status=WorkflowRunStatus.COMPLETED, started_at=ago(3600))
    )

    found = await workflows_repo.list_stuck_running(cutoff)

    assert [w.id for w in found] == [stuck.id]


async def test_list_stuck_running_includes_exact_cutoff(
    workflows_repo: AgentWorkflowRepository, organization_id
):
    cutoff = utcnow()
    workflow = await workflows_repo.create(
        _workflow(organization_id, status=WorkflowRunStatus.RUNNING, started_at=cutoff)
    )

    found = await workflows_repo.list_stuck_running(cutoff)

    assert workflow.id in {w.id for w in found}


async def test_list_stuck_running_orders_oldest_first_and_respects_limit(
    workflows_repo: AgentWorkflowRepository, organization_id
):
    cutoff = utcnow()
    newer = await workflows_repo.create(
        _workflow(organization_id, status=WorkflowRunStatus.RUNNING, started_at=ago(60))
    )
    older = await workflows_repo.create(
        _workflow(organization_id, status=WorkflowRunStatus.RUNNING, started_at=ago(7200))
    )

    found = await workflows_repo.list_stuck_running(cutoff)
    assert [w.id for w in found] == [older.id, newer.id]

    limited = await workflows_repo.list_stuck_running(cutoff, limit=1)
    assert [w.id for w in limited] == [older.id]


async def test_list_stuck_running_empty_when_none_stuck(
    workflows_repo: AgentWorkflowRepository, organization_id
):
    await workflows_repo.create(
        _workflow(organization_id, status=WorkflowRunStatus.RUNNING, started_at=soon(3600))
    )

    assert await workflows_repo.list_stuck_running(utcnow()) == []


async def test_workflow_pattern_and_status_are_plain_str_at_runtime(
    workflows_repo: AgentWorkflowRepository, organization_id
):
    workflow = await workflows_repo.create(
        _workflow(
            organization_id,
            status=WorkflowRunStatus.PENDING,
        )
    )

    assert workflow.status == WorkflowRunStatus.PENDING
    assert workflow.pattern == OrchestrationPattern.PLANNER_EXECUTOR
