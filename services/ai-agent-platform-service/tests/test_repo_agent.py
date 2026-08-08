"""Repository tests for :mod:`app.repositories.agent`.

Covers :class:`AgentRepository` and :class:`AgentVersionRepository`
against real seeded Postgres rows.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.agent import Agent, AgentVersion
from app.models.enums import AgentLifecycleStatus, AgentType
from app.repositories.agent import AgentRepository, AgentVersionRepository
from tests.conftest import ago, soon


async def _agent(
    agents_repo: AgentRepository,
    organization_id: uuid.UUID,
    *,
    slug: str = "agent",
    agent_type: AgentType = AgentType.EXECUTOR,
    status: AgentLifecycleStatus = AgentLifecycleStatus.ACTIVE,
) -> Agent:
    return await agents_repo.create(
        Agent(
            organization_id=organization_id,
            slug=slug,
            name=f"Agent {slug}",
            agent_type=agent_type,
            status=status,
        )
    )


# ---- AgentRepository.require_in_org ------------------------------------------


async def test_require_in_org_returns_agent(agents_repo, organization_id):
    agent = await _agent(agents_repo, organization_id, slug="alpha")

    found = await agents_repo.require_in_org(organization_id, agent.id)

    assert found.id == agent.id


async def test_require_in_org_raises_for_other_org(agents_repo, organization_id):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    other_org = uuid.uuid4()

    with pytest.raises(NotFoundError):
        await agents_repo.require_in_org(other_org, agent.id)


async def test_require_in_org_raises_for_unknown_id(agents_repo, organization_id):
    with pytest.raises(NotFoundError):
        await agents_repo.require_in_org(organization_id, uuid.uuid4())


# ---- get_by_slug ---------------------------------------------------------------


async def test_get_by_slug_returns_match(agents_repo, organization_id):
    agent = await _agent(agents_repo, organization_id, slug="alpha")

    found = await agents_repo.get_by_slug(organization_id, "alpha")

    assert found is not None
    assert found.id == agent.id


async def test_get_by_slug_returns_none_when_missing(agents_repo, organization_id):
    assert await agents_repo.get_by_slug(organization_id, "missing") is None


async def test_get_by_slug_is_scoped_to_org(agents_repo, organization_id):
    await _agent(agents_repo, organization_id, slug="alpha")
    other_org = uuid.uuid4()

    assert await agents_repo.get_by_slug(other_org, "alpha") is None


# ---- list_by_type ---------------------------------------------------------------


async def test_list_by_type_filters_correctly(agents_repo, organization_id):
    executor = await _agent(
        agents_repo, organization_id, slug="exec", agent_type=AgentType.EXECUTOR
    )
    await _agent(agents_repo, organization_id, slug="plan", agent_type=AgentType.PLANNER)

    found = await agents_repo.list_by_type(organization_id, AgentType.EXECUTOR)

    assert [a.id for a in found] == [executor.id]
    assert found[0].agent_type == AgentType.EXECUTOR


async def test_list_by_type_empty_when_none_match(agents_repo, organization_id):
    await _agent(agents_repo, organization_id, slug="plan", agent_type=AgentType.PLANNER)

    assert await agents_repo.list_by_type(organization_id, AgentType.RESEARCHER) == []


# ---- list_for_org ---------------------------------------------------------------


async def test_list_for_org_returns_only_own_org(agents_repo, organization_id):
    mine = await _agent(agents_repo, organization_id, slug="mine")
    other_org = uuid.uuid4()
    await _agent(agents_repo, other_org, slug="theirs")

    found = await agents_repo.list_for_org(organization_id)

    assert [a.id for a in found] == [mine.id]


# ---- list_organization_ids ------------------------------------------------------


async def test_list_organization_ids_returns_every_org_with_an_agent(agents_repo):
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    await _agent(agents_repo, org_a, slug="a")
    await _agent(agents_repo, org_b, slug="b")

    found = await agents_repo.list_organization_ids()

    assert set(found) == {org_a, org_b}


async def test_list_organization_ids_respects_limit(agents_repo):
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    await _agent(agents_repo, org_a, slug="a")
    await _agent(agents_repo, org_b, slug="b")

    found = await agents_repo.list_organization_ids(limit=1)

    assert len(found) == 1
    assert found[0] in {org_a, org_b}


# ---- list_active_without_recent_benchmark ---------------------------------------


async def test_list_active_without_recent_benchmark_excludes_benchmarked(
    agents_repo, organization_id
):
    benchmarked = await _agent(agents_repo, organization_id, slug="benchmarked")
    unbenchmarked = await _agent(agents_repo, organization_id, slug="fresh")

    found = await agents_repo.list_active_without_recent_benchmark(
        organization_id, agent_ids_with_recent_benchmark={benchmarked.id}
    )

    assert [a.id for a in found] == [unbenchmarked.id]


async def test_list_active_without_recent_benchmark_excludes_inactive_agents(
    agents_repo, organization_id
):
    await _agent(agents_repo, organization_id, slug="paused", status=AgentLifecycleStatus.PAUSED)
    active = await _agent(agents_repo, organization_id, slug="active")

    found = await agents_repo.list_active_without_recent_benchmark(
        organization_id, agent_ids_with_recent_benchmark=set()
    )

    assert [a.id for a in found] == [active.id]


async def test_list_active_without_recent_benchmark_scoped_to_org(agents_repo, organization_id):
    other_org = uuid.uuid4()
    await _agent(agents_repo, other_org, slug="theirs")

    found = await agents_repo.list_active_without_recent_benchmark(
        organization_id, agent_ids_with_recent_benchmark=set()
    )

    assert found == []


# ---- AgentVersionRepository.list_for_agent ----------------------------------------


async def test_list_for_agent_orders_newest_first(
    agent_versions_repo: AgentVersionRepository, agents_repo, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    older = await agent_versions_repo.create(
        AgentVersion(
            organization_id=organization_id,
            agent_id=agent.id,
            version_number="1.0.0",
            profile_snapshot={},
            is_current=False,
            released_at=ago(3600),
        )
    )
    newer = await agent_versions_repo.create(
        AgentVersion(
            organization_id=organization_id,
            agent_id=agent.id,
            version_number="1.1.0",
            profile_snapshot={},
            is_current=True,
            released_at=soon(3600),
        )
    )

    found = await agent_versions_repo.list_for_agent(agent.id)

    assert [v.id for v in found] == [newer.id, older.id]


async def test_list_for_agent_only_returns_own_versions(
    agent_versions_repo: AgentVersionRepository, agents_repo, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    other_agent = await _agent(agents_repo, organization_id, slug="beta")
    await agent_versions_repo.create(
        AgentVersion(
            organization_id=organization_id,
            agent_id=other_agent.id,
            version_number="1.0.0",
            profile_snapshot={},
            released_at=ago(60),
        )
    )

    assert await agent_versions_repo.list_for_agent(agent.id) == []


# ---- AgentVersionRepository.get_current --------------------------------------------


async def test_get_current_returns_current_version(
    agent_versions_repo: AgentVersionRepository, agents_repo, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    await agent_versions_repo.create(
        AgentVersion(
            organization_id=organization_id,
            agent_id=agent.id,
            version_number="1.0.0",
            profile_snapshot={},
            is_current=False,
            released_at=ago(3600),
        )
    )
    current = await agent_versions_repo.create(
        AgentVersion(
            organization_id=organization_id,
            agent_id=agent.id,
            version_number="1.1.0",
            profile_snapshot={},
            is_current=True,
            released_at=soon(3600),
        )
    )

    found = await agent_versions_repo.get_current(agent.id)

    assert found is not None
    assert found.id == current.id


async def test_get_current_returns_none_when_no_current_version(
    agent_versions_repo: AgentVersionRepository, agents_repo, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    await agent_versions_repo.create(
        AgentVersion(
            organization_id=organization_id,
            agent_id=agent.id,
            version_number="1.0.0",
            profile_snapshot={},
            is_current=False,
            released_at=ago(3600),
        )
    )

    assert await agent_versions_repo.get_current(agent.id) is None
