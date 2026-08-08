"""Tests for :mod:`app.services.agent` -- ``ProfileFields`` and
``AgentService``.

Every lifecycle transition here is exercised against real, SAVEPOINT-
isolated Postgres rows and the real recording
:class:`~tests.conftest.RecordingPublisher`; nothing is mocked.

``AgentService.register`` writes four rows in one go (agent, profile,
version, audit) and announces one event, so each registration test
re-reads through the repositories rather than trusting the returned
object -- ``db_session.expire_all()`` first, which forces a genuine
``SELECT`` back out of Postgres.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError

from app.models.enums import (
    AgentLifecycleStatus,
    AgentType,
    AuditAction,
    ModelProvider,
    ReasoningMode,
    RoutingStrategy,
)
from app.services.agent import ProfileFields

# ---------------------------------------------------------------------------
# ProfileFields
# ---------------------------------------------------------------------------


class TestProfileFields:
    def test_defaults_match_the_documented_profile_defaults(self) -> None:
        fields = ProfileFields()

        assert fields.system_prompt is None
        assert fields.model_provider == ModelProvider.OLLAMA
        assert fields.model_name == "llama3"
        assert fields.temperature == 0.2
        assert fields.max_tokens == 2048
        assert fields.reasoning_mode == ReasoningMode.TOOL_BASED
        assert fields.routing_strategy == RoutingStrategy.FALLBACK
        assert fields.fallback_providers == []
        assert fields.allowed_tool_keys == []
        assert fields.max_reasoning_steps == 8
        assert fields.extra_config == {}

    def test_is_frozen(self) -> None:
        fields = ProfileFields()

        with pytest.raises(AttributeError):
            fields.model_name = "other"  # type: ignore[misc]

    def test_to_snapshot_renders_every_field_with_stringified_enums(self) -> None:
        fields = ProfileFields(
            system_prompt="Be terse.",
            model_provider=ModelProvider.ANTHROPIC,
            model_name="claude-3",
            temperature=0.7,
            max_tokens=512,
            reasoning_mode=ReasoningMode.REFLECTION,
            routing_strategy=RoutingStrategy.COST_AWARE,
            fallback_providers=["ollama"],
            allowed_tool_keys=["probe"],
            max_reasoning_steps=3,
            extra_config={"persona": "auditor"},
        )

        assert fields.to_snapshot() == {
            "system_prompt": "Be terse.",
            "model_provider": "anthropic",
            "model_name": "claude-3",
            "temperature": 0.7,
            "max_tokens": 512,
            "reasoning_mode": "reflection",
            "routing_strategy": "cost_aware",
            "fallback_providers": ["ollama"],
            "allowed_tool_keys": ["probe"],
            "max_reasoning_steps": 3,
            "extra_config": {"persona": "auditor"},
        }

    def test_to_snapshot_copies_mutable_members(self) -> None:
        fields = ProfileFields(
            fallback_providers=["ollama"], allowed_tool_keys=["probe"], extra_config={"a": 1}
        )

        snapshot = fields.to_snapshot()
        snapshot["fallback_providers"].append("vllm")
        snapshot["allowed_tool_keys"].append("other")
        snapshot["extra_config"]["a"] = 2

        assert fields.fallback_providers == ["ollama"]
        assert fields.allowed_tool_keys == ["probe"]
        assert fields.extra_config == {"a": 1}


# ---------------------------------------------------------------------------
# AgentService.register
# ---------------------------------------------------------------------------


class TestRegister:
    async def test_creates_agent_profile_and_version_atomically(
        self, agent_service, agents_repo, profiles_repo, agent_versions_repo, db_session
    ) -> None:
        profile_fields = ProfileFields(
            system_prompt="You audit things.",
            model_provider=ModelProvider.OLLAMA,
            model_name="llama3",
            reasoning_mode=ReasoningMode.PLAN_AND_EXECUTE,
            allowed_tool_keys=["probe"],
        )
        organization_id = uuid.uuid4()

        agent = await agent_service.register(
            organization_id=organization_id,
            slug="auditor",
            name="Auditor",
            agent_type=AgentType.COMPLIANCE,
            profile=profile_fields,
            registered_by="operator-1",
        )

        db_session.expire_all()
        stored = await agents_repo.get_by_slug(organization_id, "auditor")
        profile = await profiles_repo.get_for_agent(agent.id)
        version = await agent_versions_repo.get_current(agent.id)

        assert stored is not None
        assert profile is not None
        assert version is not None
        assert stored.id == agent.id
        assert profile.agent_id == agent.id
        assert version.agent_id == agent.id

    async def test_agent_row_is_active_and_versioned(self, agent_service, organization_id) -> None:
        agent = await agent_service.register(
            organization_id=organization_id,
            slug="executor",
            name="Executor",
            agent_type=AgentType.EXECUTOR,
            description="Does the work.",
            owner_id="team-platform",
            tags=["core", "beta"],
            profile=ProfileFields(),
        )

        assert agent.status == AgentLifecycleStatus.ACTIVE
        assert agent.current_version_number == "1.0.0"
        assert agent.consecutive_failures == 0
        assert agent.last_executed_at is None
        assert agent.description == "Does the work."
        assert agent.owner_id == "team-platform"
        assert agent.tags == ["core", "beta"]
        assert agent.agent_type == AgentType.EXECUTOR

    async def test_optional_identity_fields_default_to_empty(
        self, agent_service, organization_id
    ) -> None:
        agent = await agent_service.register(
            organization_id=organization_id,
            slug="minimal",
            name="Minimal",
            agent_type=AgentType.CUSTOM,
            profile=ProfileFields(),
        )

        assert agent.description is None
        assert agent.owner_id is None
        assert agent.tags == []

    async def test_profile_row_carries_every_supplied_field(
        self, agent_service, profiles_repo, organization_id
    ) -> None:
        agent = await agent_service.register(
            organization_id=organization_id,
            slug="tuned",
            name="Tuned",
            agent_type=AgentType.RESEARCHER,
            profile=ProfileFields(
                system_prompt="Research carefully.",
                model_provider=ModelProvider.VLLM,
                model_name="mistral",
                temperature=0.9,
                max_tokens=256,
                reasoning_mode=ReasoningMode.TREE_OF_THOUGHT,
                routing_strategy=RoutingStrategy.LATENCY_AWARE,
                fallback_providers=["ollama", "local"],
                allowed_tool_keys=["probe", "lookup"],
                max_reasoning_steps=4,
                extra_config={"depth": 2},
            ),
        )

        profile = await profiles_repo.require_for_agent(agent.id)

        assert profile.organization_id == organization_id
        assert profile.system_prompt == "Research carefully."
        assert profile.model_provider == ModelProvider.VLLM
        assert profile.model_name == "mistral"
        assert profile.temperature == 0.9
        assert profile.max_tokens == 256
        assert profile.reasoning_mode == ReasoningMode.TREE_OF_THOUGHT
        assert profile.routing_strategy == RoutingStrategy.LATENCY_AWARE
        assert profile.fallback_providers == ["ollama", "local"]
        assert profile.allowed_tool_keys == ["probe", "lookup"]
        assert profile.max_reasoning_steps == 4
        assert profile.extra_config == {"depth": 2}

    async def test_first_version_snapshots_the_profile(
        self, agent_service, agent_versions_repo, organization_id
    ) -> None:
        fields = ProfileFields(system_prompt="Snapshot me.", allowed_tool_keys=["probe"])

        agent = await agent_service.register(
            organization_id=organization_id,
            slug="snapshotted",
            name="Snapshotted",
            agent_type=AgentType.PLANNER,
            profile=fields,
            registered_by="operator-2",
        )

        versions = await agent_versions_repo.list_for_agent(agent.id)

        assert len(versions) == 1
        assert versions[0].version_number == "1.0.0"
        assert versions[0].is_current is True
        assert versions[0].released_by == "operator-2"
        assert versions[0].released_at is not None
        assert versions[0].profile_snapshot == fields.to_snapshot()

    async def test_records_an_audit_entry(self, agent_service, audit_repo, organization_id) -> None:
        agent = await agent_service.register(
            organization_id=organization_id,
            slug="audited",
            name="Audited",
            agent_type=AgentType.MONITORING,
            profile=ProfileFields(),
            registered_by="operator-3",
        )

        entries = await audit_repo.list_for_entity("agent", agent.id)

        assert len(entries) == 1
        assert entries[0].action == AuditAction.AGENT_REGISTERED
        assert entries[0].entity_reference == "audited"
        assert entries[0].actor_id == "operator-3"
        assert entries[0].succeeded is True
        assert entries[0].summary == "Agent 'audited' registered and activated."

    async def test_publishes_agent_registered(
        self, agent_service, publisher, organization_id
    ) -> None:
        agent = await agent_service.register(
            organization_id=organization_id,
            slug="announced",
            name="Announced",
            agent_type=AgentType.COORDINATOR,
            profile=ProfileFields(),
        )

        assert publisher.names == ["AgentRegistered"]
        assert publisher.events[0].organization_id == organization_id
        assert publisher.events[0].payload == {"agent_id": str(agent.id), "slug": "announced"}

    async def test_duplicate_slug_in_same_org_conflicts(
        self, agent_service, organization_id
    ) -> None:
        await agent_service.register(
            organization_id=organization_id,
            slug="duplicated",
            name="First",
            agent_type=AgentType.EXECUTOR,
            profile=ProfileFields(),
        )

        with pytest.raises(ConflictError, match="'duplicated' is already registered"):
            await agent_service.register(
                organization_id=organization_id,
                slug="duplicated",
                name="Second",
                agent_type=AgentType.EXECUTOR,
                profile=ProfileFields(),
            )

    async def test_duplicate_slug_writes_nothing_extra(
        self, agent_service, agents_repo, publisher, organization_id
    ) -> None:
        await agent_service.register(
            organization_id=organization_id,
            slug="duplicated",
            name="First",
            agent_type=AgentType.EXECUTOR,
            profile=ProfileFields(),
        )

        with pytest.raises(ConflictError):
            await agent_service.register(
                organization_id=organization_id,
                slug="duplicated",
                name="Second",
                agent_type=AgentType.EXECUTOR,
                profile=ProfileFields(),
            )

        assert len(await agents_repo.list_for_org(organization_id)) == 1
        assert publisher.names == ["AgentRegistered"]

    async def test_same_slug_in_another_org_is_allowed(
        self, agent_service, agents_repo, organization_id
    ) -> None:
        other_org = uuid.uuid4()

        first = await agent_service.register(
            organization_id=organization_id,
            slug="shared-slug",
            name="Ours",
            agent_type=AgentType.EXECUTOR,
            profile=ProfileFields(),
        )
        second = await agent_service.register(
            organization_id=other_org,
            slug="shared-slug",
            name="Theirs",
            agent_type=AgentType.EXECUTOR,
            profile=ProfileFields(),
        )

        assert first.id != second.id
        assert len(await agents_repo.list_for_org(organization_id)) == 1
        assert len(await agents_repo.list_for_org(other_org)) == 1


# ---------------------------------------------------------------------------
# AgentService.update
# ---------------------------------------------------------------------------


class TestUpdate:
    async def test_updates_every_supplied_field(
        self, agent_service, agents_repo, make_agent, db_session, organization_id
    ) -> None:
        agent = await make_agent(slug="updatable", name="Before", tags=["old"])

        await agent_service.update(
            agent,
            name="After",
            description="A new description.",
            tags=["new", "shiny"],
            owner_id="team-b",
        )

        db_session.expire_all()
        stored = await agents_repo.get_by_slug(organization_id, "updatable")

        assert stored is not None
        assert stored.name == "After"
        assert stored.description == "A new description."
        assert stored.tags == ["new", "shiny"]
        assert stored.owner_id == "team-b"

    async def test_none_leaves_each_field_untouched(self, agent_service, make_agent) -> None:
        agent = await make_agent(
            slug="untouched",
            name="Original",
            description="Original description.",
            tags=["keep"],
            owner_id="team-a",
        )

        updated = await agent_service.update(agent)

        assert updated.name == "Original"
        assert updated.description == "Original description."
        assert updated.tags == ["keep"]
        assert updated.owner_id == "team-a"

    async def test_updates_only_the_named_field(self, agent_service, make_agent) -> None:
        agent = await make_agent(slug="partial", name="Original", tags=["keep"])

        updated = await agent_service.update(agent, name="Renamed")

        assert updated.name == "Renamed"
        assert updated.tags == ["keep"]

    async def test_tags_are_copied_not_aliased(self, agent_service, make_agent) -> None:
        agent = await make_agent(slug="copied")
        caller_tags = ["one"]

        updated = await agent_service.update(agent, tags=caller_tags)
        caller_tags.append("two")

        assert updated.tags == ["one"]

    async def test_update_publishes_nothing(self, agent_service, make_agent, publisher) -> None:
        agent = await make_agent(slug="quiet")

        await agent_service.update(agent, name="Renamed")

        assert publisher.names == ["AgentRegistered"]


# ---------------------------------------------------------------------------
# AgentService.pause / resume
# ---------------------------------------------------------------------------


class TestPauseResume:
    async def test_pause_moves_active_to_paused(
        self, agent_service, agents_repo, make_agent, db_session, organization_id
    ) -> None:
        agent = await make_agent(slug="pausable")

        paused = await agent_service.pause(agent)

        db_session.expire_all()
        stored = await agents_repo.get_by_slug(organization_id, "pausable")

        assert paused.status == AgentLifecycleStatus.PAUSED
        assert stored is not None
        assert stored.status == AgentLifecycleStatus.PAUSED

    async def test_pausing_an_already_paused_agent_conflicts(
        self, agent_service, make_agent
    ) -> None:
        agent = await make_agent(slug="twice-paused")
        await agent_service.pause(agent)

        with pytest.raises(ConflictError, match="is paused, not active; cannot pause"):
            await agent_service.pause(agent)

    async def test_pausing_a_retired_agent_conflicts(self, agent_service, make_agent) -> None:
        agent = await make_agent(slug="retired-then-paused")
        await agent_service.retire(agent)

        with pytest.raises(ConflictError, match="is retired, not active; cannot pause"):
            await agent_service.pause(agent)

    async def test_resume_moves_paused_to_active(
        self, agent_service, agents_repo, make_agent, db_session, organization_id
    ) -> None:
        agent = await make_agent(slug="resumable")
        await agent_service.pause(agent)

        resumed = await agent_service.resume(agent)

        db_session.expire_all()
        stored = await agents_repo.get_by_slug(organization_id, "resumable")

        assert resumed.status == AgentLifecycleStatus.ACTIVE
        assert stored is not None
        assert stored.status == AgentLifecycleStatus.ACTIVE

    async def test_resuming_an_active_agent_conflicts(self, agent_service, make_agent) -> None:
        agent = await make_agent(slug="already-active")

        with pytest.raises(ConflictError, match="is active, not paused; cannot resume"):
            await agent_service.resume(agent)

    async def test_pause_resume_round_trip_keeps_identity(self, agent_service, make_agent) -> None:
        agent = await make_agent(slug="round-trip")

        paused = await agent_service.pause(agent)
        resumed = await agent_service.resume(paused)

        assert resumed.id == agent.id
        assert resumed.status == AgentLifecycleStatus.ACTIVE


# ---------------------------------------------------------------------------
# AgentService.retire
# ---------------------------------------------------------------------------


class TestRetire:
    async def test_sets_retired_status_and_soft_deletes(
        self, agent_service, agents_repo, make_agent, organization_id
    ) -> None:
        agent = await make_agent(slug="retirable")

        retired = await agent_service.retire(agent, retired_by="operator-9")

        assert retired.status == AgentLifecycleStatus.RETIRED
        assert retired.is_active is False
        assert await agents_repo.get_by_slug(organization_id, "retirable") is None
        assert await agents_repo.list_for_org(organization_id) == []

    async def test_retiring_a_paused_agent_is_allowed(self, agent_service, make_agent) -> None:
        agent = await make_agent(slug="paused-then-retired")
        await agent_service.pause(agent)

        retired = await agent_service.retire(agent)

        assert retired.status == AgentLifecycleStatus.RETIRED

    async def test_records_a_retirement_audit_entry(
        self, agent_service, audit_repo, make_agent
    ) -> None:
        agent = await make_agent(slug="audited-retirement")

        await agent_service.retire(agent, retired_by="operator-9")

        entries = await audit_repo.list_for_entity("agent", agent.id)
        actions = [entry.action for entry in entries]

        assert AuditAction.AGENT_RETIRED in actions
        retirement = next(entry for entry in entries if entry.action == AuditAction.AGENT_RETIRED)
        assert retirement.actor_id == "operator-9"
        assert retirement.entity_reference == "audited-retirement"
        assert retirement.summary == "Agent 'audited-retirement' retired."

    async def test_retirement_actor_is_optional(
        self, agent_service, audit_repo, make_agent
    ) -> None:
        agent = await make_agent(slug="anonymous-retirement")

        await agent_service.retire(agent)

        retirement = next(
            entry
            for entry in await audit_repo.list_for_entity("agent", agent.id)
            if entry.action == AuditAction.AGENT_RETIRED
        )
        assert retirement.actor_id is None

    async def test_retire_publishes_nothing(self, agent_service, make_agent, publisher) -> None:
        agent = await make_agent(slug="silent-retirement")

        await agent_service.retire(agent)

        assert publisher.names == ["AgentRegistered"]
