"""Repository tests for :mod:`app.repositories.execution` and
:mod:`app.repositories.memory`.

Covers :class:`AgentExecutionRepository` and :class:`AgentMemoryRepository`
against real seeded Postgres rows.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.agent import Agent
from app.models.enums import AgentLifecycleStatus, AgentType, MemoryScope
from app.models.execution import AgentExecution
from app.models.memory import AgentMemory
from app.models.task import AgentTask
from app.repositories.agent import AgentRepository
from app.repositories.execution import AgentExecutionRepository
from app.repositories.memory import AgentMemoryRepository
from app.repositories.task import AgentTaskRepository
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


async def _task(
    tasks_repo: AgentTaskRepository,
    organization_id: uuid.UUID,
    *,
    agent_id: uuid.UUID | None = None,
) -> AgentTask:
    return await tasks_repo.create(
        AgentTask(
            organization_id=organization_id,
            agent_id=agent_id,
            task_type="generic",
            scheduled_at=utcnow(),
        )
    )


def _execution(
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    task_id: uuid.UUID | None = None,
    started_at=None,
) -> AgentExecution:
    return AgentExecution(
        organization_id=organization_id,
        agent_id=agent_id,
        task_id=task_id,
        started_at=started_at or utcnow(),
    )


def _memory(
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    scope: MemoryScope = MemoryScope.SHORT_TERM,
    key: str = "fact",
    summary: str | None = None,
    session_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    expires_at=None,
    created_at=None,
) -> AgentMemory:
    kwargs: dict[str, object] = {
        "organization_id": organization_id,
        "agent_id": agent_id,
        "scope": scope,
        "key": key,
        "summary": summary,
        "session_id": session_id,
        "task_id": task_id,
        "expires_at": expires_at,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return AgentMemory(**kwargs)


# ---- AgentExecutionRepository.require_in_org ------------------------------------


async def test_execution_require_in_org_returns_execution(
    executions_repo: AgentExecutionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    execution = await executions_repo.create(_execution(organization_id, agent.id))

    found = await executions_repo.require_in_org(organization_id, execution.id)

    assert found.id == execution.id


async def test_execution_require_in_org_raises_for_other_org(
    executions_repo: AgentExecutionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    execution = await executions_repo.create(_execution(organization_id, agent.id))

    with pytest.raises(NotFoundError):
        await executions_repo.require_in_org(uuid.uuid4(), execution.id)


async def test_execution_require_in_org_raises_for_unknown_id(
    executions_repo: AgentExecutionRepository, organization_id
):
    with pytest.raises(NotFoundError):
        await executions_repo.require_in_org(organization_id, uuid.uuid4())


# ---- AgentExecutionRepository.list_for_agent --------------------------------------


async def test_execution_list_for_agent_orders_newest_first(
    executions_repo: AgentExecutionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    older = await executions_repo.create(
        _execution(organization_id, agent.id, started_at=ago(3600))
    )
    newer = await executions_repo.create(
        _execution(organization_id, agent.id, started_at=soon(3600))
    )

    found = await executions_repo.list_for_agent(agent.id)

    assert [e.id for e in found] == [newer.id, older.id]


async def test_execution_list_for_agent_respects_limit(
    executions_repo: AgentExecutionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    await executions_repo.create(_execution(organization_id, agent.id, started_at=ago(10)))
    await executions_repo.create(_execution(organization_id, agent.id, started_at=ago(20)))

    found = await executions_repo.list_for_agent(agent.id, limit=1)

    assert len(found) == 1


async def test_execution_list_for_agent_scoped_to_agent(
    executions_repo: AgentExecutionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    other_agent = await _agent(agents_repo, organization_id, slug="beta")
    await executions_repo.create(_execution(organization_id, other_agent.id))

    assert await executions_repo.list_for_agent(agent.id) == []


# ---- AgentExecutionRepository.list_for_task --------------------------------------


async def test_execution_list_for_task_filters_by_task(
    executions_repo: AgentExecutionRepository,
    agents_repo: AgentRepository,
    tasks_repo: AgentTaskRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    task = await _task(tasks_repo, organization_id, agent_id=agent.id)
    other_task = await _task(tasks_repo, organization_id, agent_id=agent.id)
    matching = await executions_repo.create(_execution(organization_id, agent.id, task_id=task.id))
    await executions_repo.create(_execution(organization_id, agent.id, task_id=other_task.id))
    await executions_repo.create(_execution(organization_id, agent.id, task_id=None))

    found = await executions_repo.list_for_task(task.id)

    assert [e.id for e in found] == [matching.id]


# ---- AgentExecutionRepository.list_in_window --------------------------------------


async def test_execution_list_in_window_boundaries(
    executions_repo: AgentExecutionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    since = ago(3600)
    until = soon(0)
    at_lower = await executions_repo.create(_execution(organization_id, agent.id, started_at=since))
    inside = await executions_repo.create(
        _execution(organization_id, agent.id, started_at=ago(1800))
    )
    at_upper_excluded = await executions_repo.create(
        _execution(organization_id, agent.id, started_at=until)
    )
    before = await executions_repo.create(
        _execution(organization_id, agent.id, started_at=ago(7200))
    )

    found = await executions_repo.list_in_window(organization_id, since=since, until=until)

    found_ids = {e.id for e in found}
    assert found_ids == {at_lower.id, inside.id}
    assert at_upper_excluded.id not in found_ids
    assert before.id not in found_ids


async def test_execution_list_in_window_scoped_to_org(
    executions_repo: AgentExecutionRepository, agents_repo: AgentRepository, organization_id
):
    other_org = uuid.uuid4()
    other_agent = await _agent(agents_repo, other_org, slug="theirs")
    await executions_repo.create(_execution(other_org, other_agent.id, started_at=ago(60)))

    found = await executions_repo.list_in_window(organization_id, since=ago(3600), until=soon(3600))

    assert found == []


# ---- AgentMemoryRepository.list_live -------------------------------------------


async def test_list_live_excludes_expired_and_includes_permanent(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    moment = utcnow()
    permanent = await memory_repo.create(
        _memory(organization_id, agent.id, key="permanent", expires_at=None)
    )
    live = await memory_repo.create(
        _memory(organization_id, agent.id, key="live", expires_at=soon(3600))
    )
    await memory_repo.create(_memory(organization_id, agent.id, key="expired", expires_at=ago(60)))

    found = await memory_repo.list_live(agent.id, MemoryScope.SHORT_TERM, moment)

    assert {m.id for m in found} == {permanent.id, live.id}


async def test_list_live_excludes_exact_expiry_moment(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    moment = utcnow()
    await memory_repo.create(
        _memory(organization_id, agent.id, key="expires-now", expires_at=moment)
    )

    found = await memory_repo.list_live(agent.id, MemoryScope.SHORT_TERM, moment)

    assert found == []


async def test_list_live_filters_by_scope(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    short_term = await memory_repo.create(
        _memory(organization_id, agent.id, scope=MemoryScope.SHORT_TERM, key="short")
    )
    await memory_repo.create(
        _memory(organization_id, agent.id, scope=MemoryScope.LONG_TERM, key="long")
    )

    found = await memory_repo.list_live(agent.id, MemoryScope.SHORT_TERM, utcnow())

    assert [m.id for m in found] == [short_term.id]


async def test_list_live_narrows_by_session_id(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    session_id = uuid.uuid4()
    other_session_id = uuid.uuid4()
    matching = await memory_repo.create(
        _memory(
            organization_id, agent.id, scope=MemoryScope.SESSION, key="k", session_id=session_id
        )
    )
    await memory_repo.create(
        _memory(
            organization_id,
            agent.id,
            scope=MemoryScope.SESSION,
            key="k2",
            session_id=other_session_id,
        )
    )

    found = await memory_repo.list_live(
        agent.id, MemoryScope.SESSION, utcnow(), session_id=session_id
    )

    assert [m.id for m in found] == [matching.id]


async def test_list_live_narrows_by_task_id(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    task_id = uuid.uuid4()
    other_task_id = uuid.uuid4()
    matching = await memory_repo.create(
        _memory(organization_id, agent.id, scope=MemoryScope.TASK, key="k", task_id=task_id)
    )
    await memory_repo.create(
        _memory(organization_id, agent.id, scope=MemoryScope.TASK, key="k2", task_id=other_task_id)
    )

    found = await memory_repo.list_live(agent.id, MemoryScope.TASK, utcnow(), task_id=task_id)

    assert [m.id for m in found] == [matching.id]


# ---- AgentMemoryRepository.list_for_agent ---------------------------------------


async def test_list_for_agent_includes_expired(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    expired = await memory_repo.create(
        _memory(organization_id, agent.id, key="expired", expires_at=ago(60))
    )
    live = await memory_repo.create(_memory(organization_id, agent.id, key="live", expires_at=None))

    found = await memory_repo.list_for_agent(agent.id)

    assert {m.id for m in found} == {expired.id, live.id}


# ---- AgentMemoryRepository.get_by_key -------------------------------------------


async def test_get_by_key_returns_match_regardless_of_expiry(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    memory = await memory_repo.create(
        _memory(organization_id, agent.id, key="k", expires_at=ago(60))
    )

    found = await memory_repo.get_by_key(agent.id, MemoryScope.SHORT_TERM, "k")

    assert found is not None
    assert found.id == memory.id


async def test_get_by_key_returns_none_when_missing(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)

    assert await memory_repo.get_by_key(agent.id, MemoryScope.SHORT_TERM, "missing") is None


async def test_get_by_key_narrows_by_session_and_task(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    session_id = uuid.uuid4()
    matching = await memory_repo.create(
        _memory(
            organization_id,
            agent.id,
            scope=MemoryScope.SESSION,
            key="k",
            session_id=session_id,
        )
    )
    await memory_repo.create(
        _memory(
            organization_id,
            agent.id,
            scope=MemoryScope.SESSION,
            key="k",
            session_id=uuid.uuid4(),
        )
    )

    found = await memory_repo.get_by_key(agent.id, MemoryScope.SESSION, "k", session_id=session_id)

    assert found is not None
    assert found.id == matching.id


async def test_get_by_key_narrows_by_task_id(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    task_id = uuid.uuid4()
    matching = await memory_repo.create(
        _memory(organization_id, agent.id, scope=MemoryScope.TASK, key="k", task_id=task_id)
    )
    await memory_repo.create(
        _memory(organization_id, agent.id, scope=MemoryScope.TASK, key="k", task_id=uuid.uuid4())
    )

    found = await memory_repo.get_by_key(agent.id, MemoryScope.TASK, "k", task_id=task_id)

    assert found is not None
    assert found.id == matching.id


# ---- AgentMemoryRepository.search_for_agent -------------------------------------


async def test_search_for_agent_matches_key(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    matching = await memory_repo.create(
        _memory(organization_id, agent.id, key="user-preferred-language")
    )
    await memory_repo.create(_memory(organization_id, agent.id, key="unrelated"))

    found = await memory_repo.search_for_agent(agent.id, "preferred")

    assert [m.id for m in found] == [matching.id]


async def test_search_for_agent_matches_summary(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    matching = await memory_repo.create(
        _memory(organization_id, agent.id, key="k1", summary="Likes dark mode UI")
    )
    await memory_repo.create(
        _memory(organization_id, agent.id, key="k2", summary="Prefers light mode")
    )

    found = await memory_repo.search_for_agent(agent.id, "dark")

    assert [m.id for m in found] == [matching.id]


async def test_search_for_agent_filters_by_scope(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    short_term = await memory_repo.create(
        _memory(organization_id, agent.id, scope=MemoryScope.SHORT_TERM, key="matching-term")
    )
    await memory_repo.create(
        _memory(organization_id, agent.id, scope=MemoryScope.LONG_TERM, key="matching-term")
    )

    found = await memory_repo.search_for_agent(agent.id, "matching", scope=MemoryScope.SHORT_TERM)

    assert [m.id for m in found] == [short_term.id]


# ---- AgentMemoryRepository.delete_expired ---------------------------------------


async def test_delete_expired_removes_only_expired_and_returns_count(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    moment = utcnow()
    await memory_repo.create(_memory(organization_id, agent.id, key="expired", expires_at=ago(60)))
    live = await memory_repo.create(
        _memory(organization_id, agent.id, key="live", expires_at=soon(3600))
    )
    permanent = await memory_repo.create(
        _memory(organization_id, agent.id, key="permanent", expires_at=None)
    )

    removed = await memory_repo.delete_expired(agent.id, moment)

    assert removed == 1
    remaining = await memory_repo.list_for_agent(agent.id)
    assert {m.id for m in remaining} == {live.id, permanent.id}


async def test_delete_expired_includes_exact_moment(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    moment = utcnow()
    await memory_repo.create(
        _memory(organization_id, agent.id, key="expires-now", expires_at=moment)
    )

    removed = await memory_repo.delete_expired(agent.id, moment)

    assert removed == 1


async def test_delete_expired_returns_zero_when_none_expired(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    await memory_repo.create(_memory(organization_id, agent.id, key="live", expires_at=soon(3600)))

    assert await memory_repo.delete_expired(agent.id, utcnow()) == 0


# ---- AgentMemoryRepository.count_created_in_window --------------------------------


async def test_count_created_in_window_boundaries(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    since = ago(3600)
    until = soon(0)
    await memory_repo.create(_memory(organization_id, agent.id, key="at-lower", created_at=since))
    await memory_repo.create(_memory(organization_id, agent.id, key="inside", created_at=ago(1800)))
    await memory_repo.create(
        _memory(organization_id, agent.id, key="at-upper-excluded", created_at=until)
    )
    await memory_repo.create(_memory(organization_id, agent.id, key="before", created_at=ago(7200)))

    count = await memory_repo.count_created_in_window(organization_id, since=since, until=until)

    assert count == 2


async def test_count_created_in_window_scoped_to_org(
    memory_repo: AgentMemoryRepository, agents_repo: AgentRepository, organization_id
):
    other_org = uuid.uuid4()
    other_agent = await _agent(agents_repo, other_org, slug="theirs")
    await memory_repo.create(_memory(other_org, other_agent.id, key="theirs"))

    count = await memory_repo.count_created_in_window(
        organization_id, since=ago(3600), until=soon(3600)
    )

    assert count == 0
