"""Repository tests for :mod:`app.repositories.profile` and
:mod:`app.repositories.session`.

Covers :class:`AgentProfileRepository` and :class:`AgentSessionRepository`
against real seeded Postgres rows.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.agent import Agent
from app.models.enums import AgentLifecycleStatus, AgentType, SessionStatus
from app.models.profile import AgentProfile
from app.models.session import AgentSession
from app.repositories.agent import AgentRepository
from app.repositories.profile import AgentProfileRepository
from app.repositories.session import AgentSessionRepository
from tests.conftest import ago, utcnow


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


def _session(
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    status: SessionStatus = SessionStatus.ACTIVE,
    started_at=None,
    last_active_at=None,
) -> AgentSession:
    now = utcnow()
    return AgentSession(
        organization_id=organization_id,
        agent_id=agent_id,
        status=status,
        started_at=started_at or now,
        last_active_at=last_active_at or now,
    )


# ---- AgentProfileRepository.get_for_agent -----------------------------------------


async def test_get_for_agent_returns_profile(
    profiles_repo: AgentProfileRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    profile = await profiles_repo.create(
        AgentProfile(organization_id=organization_id, agent_id=agent.id)
    )

    found = await profiles_repo.get_for_agent(agent.id)

    assert found is not None
    assert found.id == profile.id


async def test_get_for_agent_returns_none_when_missing(
    profiles_repo: AgentProfileRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)

    assert await profiles_repo.get_for_agent(agent.id) is None


async def test_get_for_agent_scoped_to_agent(
    profiles_repo: AgentProfileRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    other_agent = await _agent(agents_repo, organization_id, slug="beta")
    await profiles_repo.create(
        AgentProfile(organization_id=organization_id, agent_id=other_agent.id)
    )

    assert await profiles_repo.get_for_agent(agent.id) is None


# ---- AgentProfileRepository.require_for_agent -------------------------------------


async def test_require_for_agent_returns_profile(
    profiles_repo: AgentProfileRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    profile = await profiles_repo.create(
        AgentProfile(organization_id=organization_id, agent_id=agent.id)
    )

    found = await profiles_repo.require_for_agent(agent.id)

    assert found.id == profile.id


async def test_require_for_agent_raises_when_missing(
    profiles_repo: AgentProfileRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)

    with pytest.raises(NotFoundError):
        await profiles_repo.require_for_agent(agent.id)


# ---- AgentSessionRepository.require_in_org -----------------------------------------


async def test_session_require_in_org_returns_session(
    sessions_repo: AgentSessionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    session = await sessions_repo.create(_session(organization_id, agent.id))

    found = await sessions_repo.require_in_org(organization_id, session.id)

    assert found.id == session.id


async def test_session_require_in_org_raises_for_other_org(
    sessions_repo: AgentSessionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    session = await sessions_repo.create(_session(organization_id, agent.id))

    with pytest.raises(NotFoundError):
        await sessions_repo.require_in_org(uuid.uuid4(), session.id)


async def test_session_require_in_org_raises_for_unknown_id(
    sessions_repo: AgentSessionRepository, organization_id
):
    with pytest.raises(NotFoundError):
        await sessions_repo.require_in_org(organization_id, uuid.uuid4())


# ---- AgentSessionRepository.list_active_for_agent -----------------------------------


async def test_list_active_for_agent_returns_only_active(
    sessions_repo: AgentSessionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    active = await sessions_repo.create(
        _session(organization_id, agent.id, status=SessionStatus.ACTIVE)
    )
    await sessions_repo.create(_session(organization_id, agent.id, status=SessionStatus.IDLE))
    await sessions_repo.create(_session(organization_id, agent.id, status=SessionStatus.CLOSED))
    await sessions_repo.create(_session(organization_id, agent.id, status=SessionStatus.EXPIRED))

    found = await sessions_repo.list_active_for_agent(agent.id)

    assert [s.id for s in found] == [active.id]
    assert found[0].status == SessionStatus.ACTIVE


async def test_list_active_for_agent_scoped_to_agent(
    sessions_repo: AgentSessionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    other_agent = await _agent(agents_repo, organization_id, slug="beta")
    await sessions_repo.create(
        _session(organization_id, other_agent.id, status=SessionStatus.ACTIVE)
    )

    assert await sessions_repo.list_active_for_agent(agent.id) == []


# ---- AgentSessionRepository.list_idle_since -----------------------------------------


async def test_list_idle_since_returns_active_and_idle_past_cutoff(
    sessions_repo: AgentSessionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    cutoff = utcnow()
    idle_active = await sessions_repo.create(
        _session(organization_id, agent.id, status=SessionStatus.ACTIVE, last_active_at=ago(3600))
    )
    idle_idle = await sessions_repo.create(
        _session(organization_id, agent.id, status=SessionStatus.IDLE, last_active_at=ago(1800))
    )
    await sessions_repo.create(
        _session(organization_id, agent.id, status=SessionStatus.ACTIVE, last_active_at=utcnow())
    )
    await sessions_repo.create(
        _session(organization_id, agent.id, status=SessionStatus.CLOSED, last_active_at=ago(3600))
    )
    await sessions_repo.create(
        _session(organization_id, agent.id, status=SessionStatus.EXPIRED, last_active_at=ago(3600))
    )

    found = await sessions_repo.list_idle_since(cutoff)

    assert {s.id for s in found} == {idle_active.id, idle_idle.id}


async def test_list_idle_since_includes_exact_cutoff(
    sessions_repo: AgentSessionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    cutoff = utcnow()
    session = await sessions_repo.create(
        _session(organization_id, agent.id, status=SessionStatus.ACTIVE, last_active_at=cutoff)
    )

    found = await sessions_repo.list_idle_since(cutoff)

    assert session.id in {s.id for s in found}


async def test_list_idle_since_excludes_recently_active(
    sessions_repo: AgentSessionRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    cutoff = ago(3600)
    await sessions_repo.create(
        _session(organization_id, agent.id, status=SessionStatus.ACTIVE, last_active_at=utcnow())
    )

    assert await sessions_repo.list_idle_since(cutoff) == []
