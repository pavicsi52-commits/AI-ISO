"""Tests for :mod:`app.memory.service` (docs/060 "MEMORY").

Everything runs against real Postgres via the ``memory_repo``/
``memory_service``/``make_agent`` fixtures from ``tests/conftest.py``.
``AgentMemory.agent_id`` is a real foreign key onto ``agents``, so every
test registers a real agent first rather than fabricating a bare UUID.
"""

from __future__ import annotations

import uuid

from app.models.enums import MemoryScope
from app.models.memory import AgentMemory
from app.repositories.memory import AgentMemoryRepository
from tests.conftest import MakeAgentFn, ago, soon, utcnow


async def _agent_id(make_agent: MakeAgentFn, slug: str = "mem-agent") -> uuid.UUID:
    agent = await make_agent(slug=slug)
    return agent.id  # type: ignore[no-any-return]


# ---- resolve_memories -------------------------------------------------------


async def test_resolve_memories_empty_when_nothing_remembered(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)

    assert await memory_service.resolve_memories(agent_id) == []


async def test_resolve_memories_returns_agent_wide_long_term(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="preferred_language",
        content={"language": "python"},
    )

    resolved = await memory_service.resolve_memories(agent_id)

    assert len(resolved) == 1
    assert resolved[0].key == "preferred_language"
    assert resolved[0].content == {"language": "python"}


async def test_resolve_memories_skips_task_scope_without_task_id(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.TASK,
        key="scratch",
        content={"v": 1},
        task_id=uuid.uuid4(),
    )

    # No task_id given to resolve_memories -- TASK-scoped rows never apply.
    assert await memory_service.resolve_memories(agent_id) == []


async def test_resolve_memories_skips_conversation_and_session_without_session_id(
    memory_service, make_agent
):
    agent_id = await _agent_id(make_agent)
    session_id = uuid.uuid4()
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.CONVERSATION,
        key="topic",
        content={"v": 1},
        session_id=session_id,
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SESSION,
        key="topic2",
        content={"v": 2},
        session_id=session_id,
    )

    assert await memory_service.resolve_memories(agent_id) == []


async def test_resolve_memories_includes_task_scope_when_task_id_given(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    task_id = uuid.uuid4()
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.TASK,
        key="scratch",
        content={"v": 1},
        task_id=task_id,
    )

    resolved = await memory_service.resolve_memories(agent_id, task_id=task_id)

    assert [m.key for m in resolved] == ["scratch"]


async def test_resolve_memories_filters_expired_rows(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="expired_fact",
        content={"v": 1},
        expires_at=ago(60),
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="live_fact",
        content={"v": 2},
        expires_at=soon(3600),
    )

    resolved = await memory_service.resolve_memories(agent_id)

    assert [m.key for m in resolved] == ["live_fact"]


async def test_resolve_memories_respects_explicit_moment(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="soon_to_expire",
        content={"v": 1},
        expires_at=soon(10),
    )

    # Not yet expired right now...
    assert len(await memory_service.resolve_memories(agent_id)) == 1
    # ...but treated as expired once "now" is moved past its expiry.
    future_moment = soon(3600)
    assert await memory_service.resolve_memories(agent_id, moment=future_moment) == []


async def test_resolve_memories_precedence_task_beats_long_term(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    task_id = uuid.uuid4()
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="current_plan",
        content={"plan": "broad"},
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.TASK,
        key="current_plan",
        content={"plan": "specific"},
        task_id=task_id,
    )

    resolved = await memory_service.resolve_memories(agent_id, task_id=task_id)

    # Deduplicated by key -- only the most specific scope's own value survives.
    assert len(resolved) == 1
    assert resolved[0].scope == MemoryScope.TASK
    assert resolved[0].content == {"plan": "specific"}


async def test_resolve_memories_precedence_conversation_beats_session(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    session_id = uuid.uuid4()
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SESSION,
        key="topic",
        content={"topic": "broad session topic"},
        session_id=session_id,
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.CONVERSATION,
        key="topic",
        content={"topic": "narrow conversation topic"},
        session_id=session_id,
    )

    resolved = await memory_service.resolve_memories(agent_id, session_id=session_id)

    assert len(resolved) == 1
    assert resolved[0].scope == MemoryScope.CONVERSATION
    assert resolved[0].content == {"topic": "narrow conversation topic"}


async def test_resolve_memories_orders_most_specific_scope_first(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    task_id, session_id = uuid.uuid4(), uuid.uuid4()
    for scope, key in (
        (MemoryScope.KNOWLEDGE_REFERENCE, "kg"),
        (MemoryScope.LONG_TERM, "lt"),
        (MemoryScope.SHORT_TERM, "st"),
        (MemoryScope.SESSION, "se"),
        (MemoryScope.CONVERSATION, "co"),
        (MemoryScope.TASK, "ta"),
    ):
        await memory_service.remember(
            agent_id=agent_id,
            organization_id=uuid.uuid4(),
            project_id=None,
            scope=scope,
            key=key,
            content={"v": key},
            session_id=session_id,
            task_id=task_id,
        )

    resolved = await memory_service.resolve_memories(
        agent_id, session_id=session_id, task_id=task_id
    )

    # Distinct keys, so every row survives dedup -- but only in
    # most-specific-scope-first order (_SCOPE_PRECEDENCE).
    assert [m.key for m in resolved] == ["ta", "co", "se", "st", "lt", "kg"]


async def test_resolve_memories_scoped_to_its_own_agent(memory_service, make_agent):
    agent_a = await _agent_id(make_agent, slug="mem-agent-a")
    agent_b = await _agent_id(make_agent, slug="mem-agent-b")
    await memory_service.remember(
        agent_id=agent_a,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="only_a",
        content={"v": 1},
    )

    assert await memory_service.resolve_memories(agent_b) == []
    assert [m.key for m in await memory_service.resolve_memories(agent_a)] == ["only_a"]


# ---- as_system_context -------------------------------------------------------


async def test_as_system_context_empty_string_when_nothing_remembered(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)

    assert await memory_service.as_system_context(agent_id) == ""


async def test_as_system_context_uses_summary_when_present(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="deploy_target",
        content={"cluster": "us-east-1", "namespace": "prod"},
        summary="Deploys go to the us-east-1 prod cluster.",
    )

    context = await memory_service.as_system_context(agent_id)

    assert context == (
        "Remembered context for this agent:\n"
        "- deploy_target: Deploys go to the us-east-1 prod cluster."
    )


async def test_as_system_context_falls_back_to_content_without_summary(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    content = {"cluster": "us-east-1"}
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="deploy_target",
        content=content,
    )

    context = await memory_service.as_system_context(agent_id)

    assert context == f"Remembered context for this agent:\n- deploy_target: {content}"


async def test_as_system_context_joins_multiple_memories_by_precedence(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="alpha",
        content={},
        summary="Alpha fact.",
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="beta",
        content={},
        summary="Beta fact.",
    )

    context = await memory_service.as_system_context(agent_id)

    assert context == (
        "Remembered context for this agent:\n- beta: Beta fact.\n- alpha: Alpha fact."
    )


# ---- remember -----------------------------------------------------------------


async def test_remember_creates_a_new_memory(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    organization_id = uuid.uuid4()
    project_id = uuid.uuid4()

    memory = await memory_service.remember(
        agent_id=agent_id,
        organization_id=organization_id,
        project_id=project_id,
        scope=MemoryScope.LONG_TERM,
        key="fact",
        content={"v": 1},
        summary="A fact.",
    )

    assert isinstance(memory, AgentMemory)
    assert memory.id is not None
    assert memory.agent_id == agent_id
    assert memory.organization_id == organization_id
    assert memory.project_id == project_id
    assert memory.scope == MemoryScope.LONG_TERM
    assert memory.key == "fact"
    assert memory.content == {"v": 1}
    assert memory.summary == "A fact."
    assert memory.session_id is None
    assert memory.task_id is None
    assert memory.expires_at is None


async def test_remember_short_term_scope_ignores_given_session_and_task_id(
    memory_service, make_agent
):
    agent_id = await _agent_id(make_agent)

    memory = await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="fact",
        content={"v": 1},
        session_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
    )

    # SHORT_TERM is agent-wide -- neither reference is stored, no matter
    # what the caller passed.
    assert memory.session_id is None
    assert memory.task_id is None


async def test_remember_task_scope_stores_task_id_only(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    task_id = uuid.uuid4()

    memory = await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.TASK,
        key="fact",
        content={"v": 1},
        session_id=uuid.uuid4(),
        task_id=task_id,
    )

    assert memory.task_id == task_id
    assert memory.session_id is None


async def test_remember_conversation_scope_stores_session_id_only(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    session_id = uuid.uuid4()

    memory = await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.CONVERSATION,
        key="fact",
        content={"v": 1},
        session_id=session_id,
        task_id=uuid.uuid4(),
    )

    assert memory.session_id == session_id
    assert memory.task_id is None


async def test_remember_updates_existing_key_in_place(
    memory_service, memory_repo: AgentMemoryRepository, make_agent
):
    agent_id = await _agent_id(make_agent)
    first = await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="current_plan",
        content={"step": 1},
        summary="Step one.",
    )

    second = await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="current_plan",
        content={"step": 2},
        summary="Step two.",
    )

    assert second.id == first.id
    assert second.content == {"step": 2}
    assert second.summary == "Step two."

    all_rows = await memory_repo.list_for_agent(agent_id)
    assert len(all_rows) == 1
    assert all_rows[0].content == {"step": 2}


async def test_remember_update_clears_expires_at_when_omitted(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="fact",
        content={"v": 1},
        expires_at=soon(3600),
    )

    updated = await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="fact",
        content={"v": 2},
    )

    assert updated.expires_at is None


async def test_remember_distinct_session_ids_create_separate_rows(
    memory_service, memory_repo: AgentMemoryRepository, make_agent
):
    agent_id = await _agent_id(make_agent)
    session_a, session_b = uuid.uuid4(), uuid.uuid4()
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.CONVERSATION,
        key="topic",
        content={"session": "a"},
        session_id=session_a,
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.CONVERSATION,
        key="topic",
        content={"session": "b"},
        session_id=session_b,
    )

    all_rows = await memory_repo.list_for_agent(agent_id)
    assert len(all_rows) == 2
    assert {row.session_id for row in all_rows} == {session_a, session_b}


async def test_remember_distinct_task_ids_create_separate_rows(
    memory_service, memory_repo: AgentMemoryRepository, make_agent
):
    agent_id = await _agent_id(make_agent)
    task_a, task_b = uuid.uuid4(), uuid.uuid4()
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.TASK,
        key="scratch",
        content={"task": "a"},
        task_id=task_a,
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.TASK,
        key="scratch",
        content={"task": "b"},
        task_id=task_b,
    )

    all_rows = await memory_repo.list_for_agent(agent_id)
    assert len(all_rows) == 2
    assert {row.task_id for row in all_rows} == {task_a, task_b}


async def test_remember_same_key_different_scopes_are_independent_rows(
    memory_service, memory_repo: AgentMemoryRepository, make_agent
):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="shared_key",
        content={"scope": "long_term"},
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="shared_key",
        content={"scope": "short_term"},
    )

    all_rows = await memory_repo.list_for_agent(agent_id)
    assert len(all_rows) == 2


# ---- search -------------------------------------------------------------------


async def test_search_matches_by_key_substring_case_insensitively(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="deployment_target",
        content={"v": 1},
    )

    found = await memory_service.search(agent_id, "DEPLOY")

    assert [m.key for m in found] == ["deployment_target"]


async def test_search_matches_by_summary_substring(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="fact",
        content={"v": 1},
        summary="The rollout uses canary releases.",
    )

    found = await memory_service.search(agent_id, "canary")

    assert [m.key for m in found] == ["fact"]


async def test_search_returns_empty_when_nothing_matches(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="fact",
        content={"v": 1},
    )

    assert await memory_service.search(agent_id, "nonexistent_needle") == []


async def test_search_filters_by_scope_when_given(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="rollout_policy",
        content={"v": 1},
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="rollout_notes",
        content={"v": 2},
    )

    found = await memory_service.search(agent_id, "rollout", scope=MemoryScope.LONG_TERM)

    assert [m.key for m in found] == ["rollout_policy"]


async def test_search_only_returns_the_given_agents_own_memories(memory_service, make_agent):
    agent_a = await _agent_id(make_agent, slug="search-agent-a")
    agent_b = await _agent_id(make_agent, slug="search-agent-b")
    await memory_service.remember(
        agent_id=agent_a,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="shared_topic",
        content={"v": 1},
    )
    await memory_service.remember(
        agent_id=agent_b,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="shared_topic",
        content={"v": 2},
    )

    found = await memory_service.search(agent_a, "shared_topic")

    assert len(found) == 1
    assert found[0].agent_id == agent_a


async def test_search_includes_expired_memories(memory_service, make_agent):
    # NOTE: AgentMemoryRepository.search_for_agent applies no expiry
    # filter at all, even though both its own and MemoryService.search's
    # docstring describe the result as "every *live* memory". This
    # documents the repository's real, current behaviour (out of scope
    # for this test group to change -- app/repositories/memory.py is not
    # one of the modules owned here).
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="stale_fact",
        content={"v": 1},
        expires_at=ago(60),
    )

    found = await memory_service.search(agent_id, "stale_fact")

    assert [m.key for m in found] == ["stale_fact"]


# ---- forget_expired -------------------------------------------------------------


async def test_forget_expired_returns_zero_when_nothing_expired(memory_service, make_agent):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="fact",
        content={"v": 1},
    )

    assert await memory_service.forget_expired(agent_id) == 0


async def test_forget_expired_removes_only_expired_rows(
    memory_service, memory_repo: AgentMemoryRepository, make_agent
):
    agent_id = await _agent_id(make_agent)
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="expired_one",
        content={"v": 1},
        expires_at=ago(120),
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="expired_two",
        content={"v": 2},
        expires_at=ago(60),
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="still_live",
        content={"v": 3},
        expires_at=soon(3600),
    )
    await memory_service.remember(
        agent_id=agent_id,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.LONG_TERM,
        key="never_expires",
        content={"v": 4},
    )

    removed = await memory_service.forget_expired(agent_id)

    assert removed == 2
    remaining = await memory_repo.list_for_agent(agent_id)
    assert {row.key for row in remaining} == {"still_live", "never_expires"}


async def test_forget_expired_scoped_to_its_own_agent(
    memory_service, memory_repo: AgentMemoryRepository, make_agent
):
    agent_a = await _agent_id(make_agent, slug="forget-agent-a")
    agent_b = await _agent_id(make_agent, slug="forget-agent-b")
    await memory_service.remember(
        agent_id=agent_a,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="expired",
        content={"v": 1},
        expires_at=ago(60),
    )
    await memory_service.remember(
        agent_id=agent_b,
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=MemoryScope.SHORT_TERM,
        key="expired",
        content={"v": 2},
        expires_at=ago(60),
    )

    removed = await memory_service.forget_expired(agent_a)

    assert removed == 1
    assert [row.key for row in await memory_repo.list_for_agent(agent_a)] == []
    assert len(await memory_repo.list_for_agent(agent_b)) == 1


def test_utcnow_helper_is_timezone_aware():
    # Sanity check on the shared test helper used throughout this
    # module's own expiry tests.
    assert utcnow().tzinfo is not None
