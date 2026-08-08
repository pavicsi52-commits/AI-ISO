"""Repository tests for :mod:`app.repositories.tool`,
:mod:`app.repositories.permission`, and :mod:`app.repositories.guardrail`.

Covers :class:`AgentToolRepository`, :class:`AgentPermissionGrantRepository`,
and :class:`AgentGuardrailRepository` against real seeded Postgres rows.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.agent import Agent
from app.models.enums import (
    AgentLifecycleStatus,
    AgentType,
    GuardrailType,
    PermissionCategory,
    PermissionGrantStatus,
    ToolKind,
)
from app.models.guardrail import AgentGuardrail
from app.models.permission import AgentPermissionGrant
from app.models.tool import AgentTool
from app.repositories.agent import AgentRepository
from app.repositories.guardrail import AgentGuardrailRepository
from app.repositories.permission import AgentPermissionGrantRepository
from app.repositories.tool import AgentToolRepository
from tests.conftest import ago


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


def _tool(
    organization_id: uuid.UUID,
    *,
    tool_key: str = "tool.key",
    enabled: bool = True,
    is_deprecated: bool = False,
    created_at=None,
) -> AgentTool:
    kwargs: dict[str, object] = {
        "organization_id": organization_id,
        "tool_key": tool_key,
        "name": f"Tool {tool_key}",
        "tool_kind": ToolKind.PYTHON,
        "enabled": enabled,
        "is_deprecated": is_deprecated,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return AgentTool(**kwargs)


def _grant(
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    category: PermissionCategory,
    status: PermissionGrantStatus = PermissionGrantStatus.PENDING,
) -> AgentPermissionGrant:
    return AgentPermissionGrant(
        organization_id=organization_id,
        agent_id=agent_id,
        category=category,
        status=status,
    )


def _guardrail(
    organization_id: uuid.UUID,
    *,
    agent_id: uuid.UUID | None = None,
    guardrail_type: GuardrailType,
) -> AgentGuardrail:
    return AgentGuardrail(
        organization_id=organization_id,
        agent_id=agent_id,
        guardrail_type=guardrail_type,
    )


# ---- AgentToolRepository.require_in_org ---------------------------------------


async def test_tool_require_in_org_returns_tool(tools_repo: AgentToolRepository, organization_id):
    tool = await tools_repo.create(_tool(organization_id))

    found = await tools_repo.require_in_org(organization_id, tool.id)

    assert found.id == tool.id


async def test_tool_require_in_org_raises_for_other_org(
    tools_repo: AgentToolRepository, organization_id
):
    tool = await tools_repo.create(_tool(organization_id))

    with pytest.raises(NotFoundError):
        await tools_repo.require_in_org(uuid.uuid4(), tool.id)


async def test_tool_require_in_org_raises_for_unknown_id(
    tools_repo: AgentToolRepository, organization_id
):
    with pytest.raises(NotFoundError):
        await tools_repo.require_in_org(organization_id, uuid.uuid4())


# ---- AgentToolRepository.get_by_key --------------------------------------------


async def test_get_by_key_returns_match(tools_repo: AgentToolRepository, organization_id):
    tool = await tools_repo.create(_tool(organization_id, tool_key="alpha.tool"))

    found = await tools_repo.get_by_key(organization_id, "alpha.tool")

    assert found is not None
    assert found.id == tool.id


async def test_get_by_key_returns_none_when_missing(
    tools_repo: AgentToolRepository, organization_id
):
    assert await tools_repo.get_by_key(organization_id, "missing.tool") is None


async def test_get_by_key_is_scoped_to_org(tools_repo: AgentToolRepository, organization_id):
    await tools_repo.create(_tool(organization_id, tool_key="alpha.tool"))
    other_org = uuid.uuid4()

    assert await tools_repo.get_by_key(other_org, "alpha.tool") is None


# ---- AgentToolRepository.list_enabled -------------------------------------------


async def test_list_enabled_excludes_disabled_and_deprecated(
    tools_repo: AgentToolRepository, organization_id
):
    enabled = await tools_repo.create(_tool(organization_id, tool_key="enabled.tool"))
    await tools_repo.create(_tool(organization_id, tool_key="disabled.tool", enabled=False))
    await tools_repo.create(_tool(organization_id, tool_key="deprecated.tool", is_deprecated=True))

    found = await tools_repo.list_enabled(organization_id)

    assert [t.id for t in found] == [enabled.id]


async def test_list_enabled_scoped_to_org(tools_repo: AgentToolRepository, organization_id):
    other_org = uuid.uuid4()
    await tools_repo.create(_tool(other_org, tool_key="theirs.tool"))

    assert await tools_repo.list_enabled(organization_id) == []


# ---- AgentToolRepository.list_for_org -------------------------------------------


async def test_tool_list_for_org_orders_newest_first(
    tools_repo: AgentToolRepository, organization_id
):
    older = await tools_repo.create(
        _tool(organization_id, tool_key="older.tool", created_at=ago(3600))
    )
    newer = await tools_repo.create(
        _tool(organization_id, tool_key="newer.tool", created_at=ago(10))
    )

    found = await tools_repo.list_for_org(organization_id)

    assert [t.id for t in found] == [newer.id, older.id]


async def test_tool_list_for_org_pagination(tools_repo: AgentToolRepository, organization_id):
    first = await tools_repo.create(_tool(organization_id, tool_key="t1", created_at=ago(30)))
    second = await tools_repo.create(_tool(organization_id, tool_key="t2", created_at=ago(20)))
    third = await tools_repo.create(_tool(organization_id, tool_key="t3", created_at=ago(10)))

    page1 = await tools_repo.list_for_org(organization_id, limit=2, offset=0)
    page2 = await tools_repo.list_for_org(organization_id, limit=2, offset=2)

    assert [t.id for t in page1] == [third.id, second.id]
    assert [t.id for t in page2] == [first.id]


async def test_tool_list_for_org_scoped_to_org(tools_repo: AgentToolRepository, organization_id):
    other_org = uuid.uuid4()
    await tools_repo.create(_tool(other_org, tool_key="theirs.tool"))

    assert await tools_repo.list_for_org(organization_id) == []


# ---- AgentPermissionGrantRepository.get_for_category -----------------------------


async def test_get_for_category_returns_match(
    permissions_repo: AgentPermissionGrantRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    grant = await permissions_repo.create(
        _grant(organization_id, agent.id, category=PermissionCategory.NETWORK)
    )

    found = await permissions_repo.get_for_category(agent.id, PermissionCategory.NETWORK)

    assert found is not None
    assert found.id == grant.id


async def test_get_for_category_returns_none_when_missing(
    permissions_repo: AgentPermissionGrantRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)

    assert await permissions_repo.get_for_category(agent.id, PermissionCategory.NETWORK) is None


# ---- AgentPermissionGrantRepository.list_granted ----------------------------------


async def test_list_granted_returns_only_granted_status(
    permissions_repo: AgentPermissionGrantRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    granted = await permissions_repo.create(
        _grant(
            organization_id,
            agent.id,
            category=PermissionCategory.NETWORK,
            status=PermissionGrantStatus.GRANTED,
        )
    )
    await permissions_repo.create(
        _grant(
            organization_id,
            agent.id,
            category=PermissionCategory.FILESYSTEM,
            status=PermissionGrantStatus.PENDING,
        )
    )
    await permissions_repo.create(
        _grant(
            organization_id,
            agent.id,
            category=PermissionCategory.DATA_ACCESS,
            status=PermissionGrantStatus.DENIED,
        )
    )
    await permissions_repo.create(
        _grant(
            organization_id,
            agent.id,
            category=PermissionCategory.DELEGATION,
            status=PermissionGrantStatus.REVOKED,
        )
    )

    found = await permissions_repo.list_granted(agent.id)

    assert [g.id for g in found] == [granted.id]
    assert found[0].status == PermissionGrantStatus.GRANTED


async def test_list_granted_scoped_to_agent(
    permissions_repo: AgentPermissionGrantRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    other_agent = await _agent(agents_repo, organization_id, slug="beta")
    await permissions_repo.create(
        _grant(
            organization_id,
            other_agent.id,
            category=PermissionCategory.NETWORK,
            status=PermissionGrantStatus.GRANTED,
        )
    )

    assert await permissions_repo.list_granted(agent.id) == []


# ---- AgentPermissionGrantRepository.list_for_agent --------------------------------


async def test_list_for_agent_returns_all_statuses(
    permissions_repo: AgentPermissionGrantRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    granted = await permissions_repo.create(
        _grant(
            organization_id,
            agent.id,
            category=PermissionCategory.NETWORK,
            status=PermissionGrantStatus.GRANTED,
        )
    )
    pending = await permissions_repo.create(
        _grant(
            organization_id,
            agent.id,
            category=PermissionCategory.FILESYSTEM,
            status=PermissionGrantStatus.PENDING,
        )
    )

    found = await permissions_repo.list_for_agent(agent.id)

    assert {g.id for g in found} == {granted.id, pending.id}


# ---- AgentGuardrailRepository.get_for_agent ---------------------------------------


async def test_get_for_agent_returns_own_override(
    guardrails_repo: AgentGuardrailRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    override = await guardrails_repo.create(
        _guardrail(organization_id, agent_id=agent.id, guardrail_type=GuardrailType.PII_DETECTION)
    )

    found = await guardrails_repo.get_for_agent(
        organization_id, agent.id, GuardrailType.PII_DETECTION
    )

    assert found is not None
    assert found.id == override.id


async def test_get_for_agent_returns_none_when_only_org_default_exists(
    guardrails_repo: AgentGuardrailRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    await guardrails_repo.create(
        _guardrail(organization_id, agent_id=None, guardrail_type=GuardrailType.PII_DETECTION)
    )

    assert (
        await guardrails_repo.get_for_agent(organization_id, agent.id, GuardrailType.PII_DETECTION)
        is None
    )


# ---- AgentGuardrailRepository.get_org_default -------------------------------------


async def test_get_org_default_returns_default(
    guardrails_repo: AgentGuardrailRepository, organization_id
):
    default = await guardrails_repo.create(
        _guardrail(organization_id, agent_id=None, guardrail_type=GuardrailType.SECRET_REDACTION)
    )

    found = await guardrails_repo.get_org_default(organization_id, GuardrailType.SECRET_REDACTION)

    assert found is not None
    assert found.id == default.id


async def test_get_org_default_returns_none_when_only_agent_override_exists(
    guardrails_repo: AgentGuardrailRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    await guardrails_repo.create(
        _guardrail(
            organization_id, agent_id=agent.id, guardrail_type=GuardrailType.SECRET_REDACTION
        )
    )

    assert (
        await guardrails_repo.get_org_default(organization_id, GuardrailType.SECRET_REDACTION)
        is None
    )


# ---- AgentGuardrailRepository.list_effective --------------------------------------


async def test_list_effective_returns_own_override_and_org_defaults(
    guardrails_repo: AgentGuardrailRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    other_agent = await _agent(agents_repo, organization_id, slug="beta")
    own_override = await guardrails_repo.create(
        _guardrail(organization_id, agent_id=agent.id, guardrail_type=GuardrailType.PII_DETECTION)
    )
    org_default = await guardrails_repo.create(
        _guardrail(organization_id, agent_id=None, guardrail_type=GuardrailType.SECRET_REDACTION)
    )
    other_override = await guardrails_repo.create(
        _guardrail(
            organization_id,
            agent_id=other_agent.id,
            guardrail_type=GuardrailType.EXECUTION_CONSTRAINT,
        )
    )

    found = await guardrails_repo.list_effective(organization_id, agent.id)

    found_ids = {g.id for g in found}
    assert found_ids == {own_override.id, org_default.id}
    assert other_override.id not in found_ids


async def test_list_effective_scoped_to_org(
    guardrails_repo: AgentGuardrailRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    other_org = uuid.uuid4()
    await guardrails_repo.create(
        _guardrail(other_org, agent_id=None, guardrail_type=GuardrailType.PII_DETECTION)
    )

    assert await guardrails_repo.list_effective(organization_id, agent.id) == []
