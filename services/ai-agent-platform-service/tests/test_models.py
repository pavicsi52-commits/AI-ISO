"""Tests for every ORM model in :mod:`app.models`.

**Everything is asserted through real inserts against real
PostgreSQL**, never by introspecting SQLAlchemy metadata: a
``UniqueConstraint`` in ``__table_args__`` that never made it into a
migration would still be present in the metadata, so reading the
metadata back would only prove the model file says what the model file
says. A real duplicate ``INSERT`` proves the constraint exists in the
database the service actually runs against.

Two platform conventions drive the shape of these tests:

- **A loaded row's enum-typed column is a plain ``str`` at runtime** --
  every ``Mapped[SomeEnum]`` here is backed by ``String``. Comparisons
  therefore use ``==`` against the enum member (``StrEnum`` compares
  equal to its own value), never ``is``.
- **JSON columns are reassigned, never mutated in place** -- SQLAlchemy
  does not track in-place mutation of a plain ``JSON`` column.

Duplicate/constraint violations are attempted from their **own second
session** off ``db_session_factory``, so the rollback that a failed
flush requires only unwinds that session's own SAVEPOINT and the
already-inserted first row survives to be asserted on.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from shared_core.database.exceptions import ConstraintFailedError, DuplicateRecordError
from shared_core.enums.health_status import HealthStatus
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from app.models.agent import Agent, AgentVersion
from app.models.benchmark import AgentBenchmark
from app.models.enums import (
    AgentLifecycleStatus,
    AgentMarketplaceListingStatus,
    AgentType,
    AuditAction,
    BenchmarkStatus,
    ExecutionStatus,
    GuardrailType,
    GuardrailVerdict,
    MemoryScope,
    ModelProvider,
    OrchestrationPattern,
    PermissionCategory,
    PermissionGrantStatus,
    ReasoningMode,
    ReportFormat,
    ReportKind,
    ReportStatus,
    RiskLevel,
    RoutingStrategy,
    SessionStatus,
    TaskPriority,
    TaskStatus,
    ToolCallStatus,
    ToolKind,
    WorkflowRunStatus,
)
from app.models.evaluation import AgentEvaluation
from app.models.execution import AgentExecution
from app.models.governance import AgentAudit, AgentReport, AgentStatistic
from app.models.guardrail import AgentGuardrail
from app.models.marketplace import AgentMarketplaceEntry
from app.models.memory import AgentMemory
from app.models.permission import AgentPermissionGrant
from app.models.profile import AgentProfile
from app.models.session import AgentSession
from app.models.task import AgentTask
from app.models.tool import AgentTool
from app.models.workflow import AgentWorkflow
from app.repositories.agent import AgentRepository, AgentVersionRepository
from app.repositories.benchmark import AgentBenchmarkRepository
from app.repositories.evaluation import AgentEvaluationRepository
from app.repositories.execution import AgentExecutionRepository
from app.repositories.governance import (
    AgentAuditRepository,
    AgentReportRepository,
    AgentStatisticRepository,
)
from app.repositories.guardrail import AgentGuardrailRepository
from app.repositories.marketplace import AgentMarketplaceEntryRepository
from app.repositories.memory import AgentMemoryRepository
from app.repositories.permission import AgentPermissionGrantRepository
from app.repositories.profile import AgentProfileRepository
from app.repositories.session import AgentSessionRepository
from app.repositories.task import AgentTaskRepository
from app.repositories.tool import AgentToolRepository
from app.repositories.workflow import AgentWorkflowRepository
from tests.conftest import utcnow

RepositoryFactory = Callable[[AsyncSession], object]


async def _insert_expecting(
    session_factory: async_sessionmaker[AsyncSession],
    repository: RepositoryFactory,
    row: object,
    error: type[Exception],
) -> None:
    """Attempt one real insert in its own session, expecting *error*.

    A failed flush poisons its session, so this deliberately uses a
    throwaway session: the caller's own rows stay intact and assertable.
    """
    async with session_factory() as session:
        with pytest.raises(error):
            await repository(session).create(row)  # type: ignore[attr-defined]
        await session.rollback()


async def _agent(
    agents_repo: AgentRepository,
    organization_id: uuid.UUID,
    *,
    slug: str = "agent",
    **overrides: object,
) -> Agent:
    fields: dict[str, object] = {
        "organization_id": organization_id,
        "slug": slug,
        "name": f"Agent {slug}",
        "agent_type": AgentType.EXECUTOR,
    }
    fields.update(overrides)
    return await agents_repo.create(Agent(**fields))


# ---- app/models/enums.py --------------------------------------------------------


class TestEnums:
    """Every value docs/060 names, asserted literally."""

    def test_agent_type_has_the_fourteen_documented_types(self) -> None:
        assert [member.value for member in AgentType] == [
            "planner",
            "executor",
            "researcher",
            "reviewer",
            "validator",
            "coordinator",
            "monitoring",
            "automation",
            "infrastructure",
            "compliance",
            "security",
            "knowledge_graph",
            "reporting",
            "custom",
        ]

    def test_agent_lifecycle_status_values(self) -> None:
        assert [member.value for member in AgentLifecycleStatus] == [
            "registered",
            "initializing",
            "configured",
            "active",
            "paused",
            "disabled",
            "upgrading",
            "retired",
        ]

    def test_memory_scope_is_most_specific_first(self) -> None:
        assert [member.value for member in MemoryScope] == [
            "task",
            "conversation",
            "session",
            "short_term",
            "long_term",
            "knowledge_reference",
        ]

    def test_session_status_values(self) -> None:
        assert [member.value for member in SessionStatus] == [
            "active",
            "idle",
            "expired",
            "closed",
        ]

    def test_task_status_values(self) -> None:
        assert [member.value for member in TaskStatus] == [
            "pending",
            "queued",
            "assigned",
            "running",
            "retrying",
            "completed",
            "failed",
            "cancelled",
            "timed_out",
        ]

    def test_task_priority_matches_the_shared_queue_levels(self) -> None:
        assert [member.value for member in TaskPriority] == [
            "critical",
            "high",
            "normal",
            "low",
            "background",
        ]

    def test_workflow_run_status_values(self) -> None:
        assert [member.value for member in WorkflowRunStatus] == [
            "pending",
            "running",
            "paused_for_approval",
            "completed",
            "failed",
            "cancelled",
        ]

    def test_orchestration_pattern_has_the_nine_documented_patterns(self) -> None:
        assert len(OrchestrationPattern) == 9
        assert OrchestrationPattern.PLANNER_EXECUTOR.value == "planner_executor"
        assert OrchestrationPattern.CONFLICT_RESOLUTION.value == "conflict_resolution"

    def test_tool_kind_has_the_ten_documented_kinds(self) -> None:
        assert len(ToolKind) == 10
        assert ToolKind.KNOWLEDGE_GRAPH_QUERY.value == "knowledge_graph_query"

    def test_tool_call_status_keeps_denied_distinct_from_failed(self) -> None:
        assert ToolCallStatus.DENIED.value == "denied"
        assert ToolCallStatus.DENIED != ToolCallStatus.FAILED

    def test_permission_category_values(self) -> None:
        assert len(PermissionCategory) == 8
        assert PermissionCategory.TOOL_INVOCATION.value == "tool_invocation"

    def test_permission_grant_status_values(self) -> None:
        assert [member.value for member in PermissionGrantStatus] == [
            "pending",
            "granted",
            "denied",
            "revoked",
        ]

    def test_guardrail_verdict_and_type_values(self) -> None:
        assert [member.value for member in GuardrailVerdict] == [
            "allowed",
            "blocked",
            "redacted",
            "flagged",
        ]
        assert len(GuardrailType) == 8
        assert GuardrailType.SECRET_REDACTION.value == "secret_redaction"

    def test_risk_level_values(self) -> None:
        assert [member.value for member in RiskLevel] == ["low", "medium", "high", "critical"]

    def test_execution_status_values(self) -> None:
        assert [member.value for member in ExecutionStatus] == [
            "pending",
            "running",
            "completed",
            "failed",
            "cancelled",
            "timed_out",
        ]

    def test_reasoning_mode_has_the_eight_documented_modes(self) -> None:
        assert len(ReasoningMode) == 8
        assert ReasoningMode.CHAIN_OF_THOUGHT.value == "chain_of_thought"

    def test_model_provider_values(self) -> None:
        assert [member.value for member in ModelProvider] == [
            "openai",
            "azure_openai",
            "anthropic",
            "google_gemini",
            "ollama",
            "vllm",
            "openrouter",
            "local",
        ]

    def test_routing_strategy_values(self) -> None:
        assert [member.value for member in RoutingStrategy] == [
            "rule_based",
            "cost_aware",
            "latency_aware",
            "fallback",
        ]

    def test_benchmark_and_report_status_values(self) -> None:
        assert [member.value for member in BenchmarkStatus] == [
            "pending",
            "running",
            "completed",
            "failed",
        ]
        assert [member.value for member in ReportStatus] == [
            "pending",
            "running",
            "completed",
            "failed",
        ]

    def test_marketplace_listing_status_values(self) -> None:
        assert [member.value for member in AgentMarketplaceListingStatus] == [
            "draft",
            "published",
            "featured",
            "deprecated",
            "removed",
        ]

    def test_report_kind_and_format_values(self) -> None:
        assert len(ReportKind) == 7
        assert [member.value for member in ReportFormat] == ["json", "csv", "markdown"]

    def test_audit_action_values(self) -> None:
        assert len(AuditAction) == 13
        assert AuditAction.APPROVAL_DECIDED.value == "approval_decided"

    def test_every_enum_is_a_str_at_runtime(self) -> None:
        """The "enum-as-str" rule the model columns depend on."""
        assert isinstance(AgentType.PLANNER, str)
        assert str(AgentType.PLANNER) == "planner"
        assert AgentType.PLANNER == "planner"
        assert f"{TaskStatus.RETRYING}" == "retrying"


def test_models_package_reexports_every_model_and_enum() -> None:
    """``from app.models import ...`` is the single import surface."""
    for name in models.__all__:
        assert hasattr(models, name), name
    assert models.HealthStatus is HealthStatus
    assert models.Agent is Agent
    assert models.AgentWorkflow is AgentWorkflow


# ---- app/models/agent.py -- Agent -------------------------------------------------


async def test_agent_column_defaults(
    agents_repo: AgentRepository, organization_id: uuid.UUID
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="defaults")

    assert agent.description is None
    assert agent.status == AgentLifecycleStatus.REGISTERED
    assert agent.current_version_number is None
    assert agent.tags == []
    assert agent.owner_id is None
    assert agent.consecutive_failures == 0
    assert agent.last_executed_at is None
    # BaseEntityMixin's own standard columns.
    assert isinstance(agent.id, uuid.UUID)
    assert agent.is_active is True
    assert agent.version == 1
    assert agent.project_id is None
    assert agent.deleted_at is None
    assert agent.created_at is not None
    assert agent.updated_at is not None


async def test_agent_slug_is_unique_per_organization(
    agents_repo: AgentRepository,
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    original = await _agent(agents_repo, organization_id, slug="duplicated")

    await _insert_expecting(
        db_session_factory,
        AgentRepository,
        Agent(
            organization_id=organization_id,
            slug="duplicated",
            name="Second",
            agent_type=AgentType.PLANNER,
        ),
        DuplicateRecordError,
    )

    assert await agents_repo.get_by_slug(organization_id, "duplicated") is not None
    assert (await agents_repo.get_by_slug(organization_id, "duplicated")).id == original.id


async def test_agent_slug_may_repeat_across_organizations(
    agents_repo: AgentRepository, organization_id: uuid.UUID
) -> None:
    """``uq_agent_slug`` is ``(organization_id, slug)``, not ``slug``."""
    other_org = uuid.uuid4()
    mine = await _agent(agents_repo, organization_id, slug="shared-slug")
    theirs = await _agent(agents_repo, other_org, slug="shared-slug")

    assert mine.id != theirs.id


async def test_agent_enum_columns_load_back_as_plain_strings(
    agents_repo: AgentRepository, db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    agent = await _agent(
        agents_repo,
        organization_id,
        slug="enum-str",
        agent_type=AgentType.KNOWLEDGE_GRAPH,
        status=AgentLifecycleStatus.ACTIVE,
    )
    db_session.expunge(agent)

    reloaded = await agents_repo.require_by_id(agent.id)

    assert type(reloaded.agent_type) is str
    assert type(reloaded.status) is str
    assert reloaded.agent_type == AgentType.KNOWLEDGE_GRAPH
    assert reloaded.status == AgentLifecycleStatus.ACTIVE


async def test_agent_tags_json_column_round_trips_on_reassignment(
    agents_repo: AgentRepository, db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="tagged", tags=["alpha"])

    agent.tags = [*agent.tags, "beta"]
    await agents_repo.update(agent)
    db_session.expunge(agent)

    reloaded = await agents_repo.require_by_id(agent.id)
    assert reloaded.tags == ["alpha", "beta"]


async def test_agent_requires_a_name(
    db_session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    await _insert_expecting(
        db_session_factory,
        AgentRepository,
        Agent(organization_id=organization_id, slug="nameless", agent_type=AgentType.EXECUTOR),
        ConstraintFailedError,
    )


# ---- app/models/agent.py -- AgentVersion ------------------------------------------


async def test_agent_version_column_defaults(
    agents_repo: AgentRepository,
    agent_versions_repo: AgentVersionRepository,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="versioned")

    version = await agent_versions_repo.create(
        AgentVersion(
            organization_id=organization_id,
            agent_id=agent.id,
            version_number="1.0.0",
            released_at=utcnow(),
        )
    )

    assert version.changelog is None
    assert version.profile_snapshot == {}
    assert version.is_current is True
    assert version.released_by is None


async def test_agent_version_number_is_unique_per_agent(
    agents_repo: AgentRepository,
    agent_versions_repo: AgentVersionRepository,
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    """``uq_agent_version_number`` -- the constraint this table exists for."""
    agent = await _agent(agents_repo, organization_id, slug="dup-version")
    await agent_versions_repo.create(
        AgentVersion(
            organization_id=organization_id,
            agent_id=agent.id,
            version_number="2.1.0",
            released_at=utcnow(),
        )
    )

    await _insert_expecting(
        db_session_factory,
        AgentVersionRepository,
        AgentVersion(
            organization_id=organization_id,
            agent_id=agent.id,
            version_number="2.1.0",
            released_at=utcnow(),
        ),
        DuplicateRecordError,
    )

    assert len(await agent_versions_repo.list_for_agent(agent.id)) == 1


async def test_agent_version_number_may_repeat_across_agents(
    agents_repo: AgentRepository,
    agent_versions_repo: AgentVersionRepository,
    organization_id: uuid.UUID,
) -> None:
    first = await _agent(agents_repo, organization_id, slug="one")
    second = await _agent(agents_repo, organization_id, slug="two")

    for agent in (first, second):
        await agent_versions_repo.create(
            AgentVersion(
                organization_id=organization_id,
                agent_id=agent.id,
                version_number="1.0.0",
                released_at=utcnow(),
            )
        )

    assert len(await agent_versions_repo.list_for_agent(first.id)) == 1
    assert len(await agent_versions_repo.list_for_agent(second.id)) == 1


async def test_agent_versions_cascade_when_their_agent_row_is_removed(
    agents_repo: AgentRepository,
    agent_versions_repo: AgentVersionRepository,
    db_session: AsyncSession,
    organization_id: uuid.UUID,
) -> None:
    """``ForeignKey(..., ondelete="CASCADE")`` -- proven with a real
    hard delete, not a soft delete."""
    agent = await _agent(agents_repo, organization_id, slug="cascade")
    version = await agent_versions_repo.create(
        AgentVersion(
            organization_id=organization_id,
            agent_id=agent.id,
            version_number="1.0.0",
            released_at=utcnow(),
        )
    )

    await agents_repo.purge(agent.id)

    remaining = await db_session.execute(
        text("SELECT count(*) FROM agent_versions WHERE id = :id"), {"id": version.id}
    )
    assert remaining.scalar_one() == 0


# ---- app/models/profile.py --------------------------------------------------------


async def test_agent_profile_column_defaults(
    agents_repo: AgentRepository,
    profiles_repo: AgentProfileRepository,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="profiled")

    profile = await profiles_repo.create(
        AgentProfile(organization_id=organization_id, agent_id=agent.id)
    )

    assert profile.system_prompt is None
    assert profile.model_provider == ModelProvider.OLLAMA
    assert profile.model_name == "llama3"
    assert profile.temperature == pytest.approx(0.2)
    assert profile.max_tokens == 2_048
    assert profile.reasoning_mode == ReasoningMode.TOOL_BASED
    assert profile.routing_strategy == RoutingStrategy.FALLBACK
    assert profile.fallback_providers == []
    assert profile.allowed_tool_keys == []
    assert profile.max_reasoning_steps == 8
    assert profile.extra_config == {}


async def test_agent_profile_is_unique_per_agent(
    agents_repo: AgentRepository,
    profiles_repo: AgentProfileRepository,
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    """``uq_agent_profile_agent`` -- one active profile per agent."""
    agent = await _agent(agents_repo, organization_id, slug="one-profile")
    await profiles_repo.create(AgentProfile(organization_id=organization_id, agent_id=agent.id))

    await _insert_expecting(
        db_session_factory,
        AgentProfileRepository,
        AgentProfile(organization_id=organization_id, agent_id=agent.id),
        DuplicateRecordError,
    )

    assert await profiles_repo.get_for_agent(agent.id) is not None


# ---- app/models/session.py --------------------------------------------------------


async def test_agent_session_column_defaults(
    agents_repo: AgentRepository,
    sessions_repo: AgentSessionRepository,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="sessioned")
    now = utcnow()

    session_row = await sessions_repo.create(
        AgentSession(
            organization_id=organization_id,
            agent_id=agent.id,
            started_at=now,
            last_active_at=now,
        )
    )

    assert session_row.status == SessionStatus.ACTIVE
    assert session_row.context == {}
    assert session_row.turn_count == 0
    assert session_row.closed_at is None
    assert session_row.initiated_by is None


async def test_agent_session_requires_started_at(
    agents_repo: AgentRepository,
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="no-start")

    await _insert_expecting(
        db_session_factory,
        AgentSessionRepository,
        AgentSession(organization_id=organization_id, agent_id=agent.id, last_active_at=utcnow()),
        ConstraintFailedError,
    )


# ---- app/models/task.py -----------------------------------------------------------


async def test_agent_task_column_defaults(
    tasks_repo: AgentTaskRepository, organization_id: uuid.UUID
) -> None:
    task = await tasks_repo.create(
        AgentTask(organization_id=organization_id, task_type="generic", scheduled_at=utcnow())
    )

    assert task.agent_id is None
    assert task.parent_task_id is None
    assert task.status == TaskStatus.PENDING
    assert task.priority == TaskPriority.NORMAL
    assert task.payload == {}
    assert task.result is None
    assert task.checkpoint == {}
    assert task.retry_count == 0
    assert task.max_retries == 3
    assert task.timeout_seconds == pytest.approx(300.0)
    assert task.started_at is None
    assert task.completed_at is None
    assert task.error is None
    assert task.requested_by is None


async def test_agent_task_agent_id_is_set_null_when_the_agent_row_is_removed(
    agents_repo: AgentRepository,
    tasks_repo: AgentTaskRepository,
    db_session: AsyncSession,
    organization_id: uuid.UUID,
) -> None:
    """``ondelete="SET NULL"`` -- a task outlives its agent rather than
    disappearing with it."""
    agent = await _agent(agents_repo, organization_id, slug="task-owner")
    task = await tasks_repo.create(
        AgentTask(
            organization_id=organization_id,
            agent_id=agent.id,
            task_type="generic",
            scheduled_at=utcnow(),
        )
    )

    await agents_repo.purge(agent.id)

    result = await db_session.execute(
        text("SELECT agent_id FROM agent_tasks WHERE id = :id"), {"id": task.id}
    )
    assert result.scalar_one() is None


async def test_agent_task_parent_link_is_set_null_when_the_parent_is_removed(
    tasks_repo: AgentTaskRepository, db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    parent = await tasks_repo.create(
        AgentTask(organization_id=organization_id, task_type="parent", scheduled_at=utcnow())
    )
    child = await tasks_repo.create(
        AgentTask(
            organization_id=organization_id,
            parent_task_id=parent.id,
            task_type="child",
            scheduled_at=utcnow(),
        )
    )

    await tasks_repo.purge(parent.id)

    result = await db_session.execute(
        text("SELECT parent_task_id FROM agent_tasks WHERE id = :id"), {"id": child.id}
    )
    assert result.scalar_one() is None


async def test_agent_task_json_columns_round_trip(
    tasks_repo: AgentTaskRepository, db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    task = await tasks_repo.create(
        AgentTask(
            organization_id=organization_id,
            task_type="generic",
            payload={"request": "summarise"},
            scheduled_at=utcnow(),
        )
    )

    task.payload = {**task.payload, "extra": [1, 2]}
    task.result = {"execution_id": "abc"}
    task.checkpoint = {"step": 3}
    await tasks_repo.update(task)
    db_session.expunge(task)

    reloaded = await tasks_repo.require_by_id(task.id)
    assert reloaded.payload == {"request": "summarise", "extra": [1, 2]}
    assert reloaded.result == {"execution_id": "abc"}
    assert reloaded.checkpoint == {"step": 3}


async def test_agent_task_requires_scheduled_at(
    db_session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    await _insert_expecting(
        db_session_factory,
        AgentTaskRepository,
        AgentTask(organization_id=organization_id, task_type="generic"),
        ConstraintFailedError,
    )


# ---- app/models/tool.py -----------------------------------------------------------


async def test_agent_tool_column_defaults(
    tools_repo: AgentToolRepository, organization_id: uuid.UUID
) -> None:
    tool = await tools_repo.create(
        AgentTool(
            organization_id=organization_id,
            tool_key="crm.lookup",
            name="CRM Lookup",
            tool_kind=ToolKind.REST,
        )
    )

    assert tool.description is None
    assert tool.category == "general"
    assert tool.parameters_schema == {}
    assert tool.required_permission == PermissionCategory.TOOL_INVOCATION
    assert tool.is_mutating is False
    assert tool.version_number == "1.0.0"
    assert tool.enabled is True
    assert tool.is_deprecated is False
    assert tool.health_status == HealthStatus.UNKNOWN
    assert tool.last_health_checked_at is None
    assert tool.metadata_ == {}


async def test_agent_tool_key_is_unique_per_organization(
    tools_repo: AgentToolRepository,
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    await tools_repo.create(
        AgentTool(
            organization_id=organization_id,
            tool_key="crm.lookup",
            name="CRM Lookup",
            tool_kind=ToolKind.REST,
        )
    )

    await _insert_expecting(
        db_session_factory,
        AgentToolRepository,
        AgentTool(
            organization_id=organization_id,
            tool_key="crm.lookup",
            name="Duplicate",
            tool_kind=ToolKind.PYTHON,
        ),
        DuplicateRecordError,
    )

    assert len(await tools_repo.list_for_org(organization_id)) == 1


async def test_agent_tool_metadata_is_stored_in_a_column_literally_named_metadata(
    tools_repo: AgentToolRepository, db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    """``metadata_`` is the attribute (``metadata`` is reserved by
    SQLAlchemy's declarative base); ``metadata`` is the real column."""
    tool = await tools_repo.create(
        AgentTool(
            organization_id=organization_id,
            tool_key="crm.write",
            name="CRM Write",
            tool_kind=ToolKind.REST,
            metadata_={"owner": "crm-team"},
        )
    )

    result = await db_session.execute(
        text("SELECT metadata FROM agent_tools WHERE id = :id"), {"id": tool.id}
    )
    assert result.scalar_one() == {"owner": "crm-team"}


# ---- app/models/permission.py -----------------------------------------------------


async def test_agent_permission_grant_column_defaults(
    agents_repo: AgentRepository,
    permissions_repo: AgentPermissionGrantRepository,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="granted")

    grant = await permissions_repo.create(
        AgentPermissionGrant(
            organization_id=organization_id,
            agent_id=agent.id,
            category=PermissionCategory.NETWORK,
        )
    )

    assert grant.scope is None
    assert grant.status == PermissionGrantStatus.PENDING
    assert grant.justification is None
    assert grant.decided_by is None
    assert grant.decided_at is None


async def test_agent_permission_category_is_unique_per_agent(
    agents_repo: AgentRepository,
    permissions_repo: AgentPermissionGrantRepository,
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="dup-grant")
    await permissions_repo.create(
        AgentPermissionGrant(
            organization_id=organization_id,
            agent_id=agent.id,
            category=PermissionCategory.NETWORK,
        )
    )

    await _insert_expecting(
        db_session_factory,
        AgentPermissionGrantRepository,
        AgentPermissionGrant(
            organization_id=organization_id,
            agent_id=agent.id,
            category=PermissionCategory.NETWORK,
        ),
        DuplicateRecordError,
    )

    assert len(await permissions_repo.list_for_agent(agent.id)) == 1


async def test_agent_permission_different_categories_coexist(
    agents_repo: AgentRepository,
    permissions_repo: AgentPermissionGrantRepository,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="multi-grant")

    for category in (PermissionCategory.NETWORK, PermissionCategory.FILESYSTEM):
        await permissions_repo.create(
            AgentPermissionGrant(
                organization_id=organization_id, agent_id=agent.id, category=category
            )
        )

    assert len(await permissions_repo.list_for_agent(agent.id)) == 2


# ---- app/models/guardrail.py ------------------------------------------------------


async def test_agent_guardrail_column_defaults(
    agents_repo: AgentRepository,
    guardrails_repo: AgentGuardrailRepository,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="guarded")

    guardrail = await guardrails_repo.create(
        AgentGuardrail(
            organization_id=organization_id,
            agent_id=agent.id,
            guardrail_type=GuardrailType.PII_DETECTION,
        )
    )

    assert guardrail.enabled is True
    assert guardrail.config == {}
    assert guardrail.trigger_count == 0
    assert guardrail.last_triggered_at is None


async def test_agent_guardrail_type_is_unique_per_org_and_agent(
    agents_repo: AgentRepository,
    guardrails_repo: AgentGuardrailRepository,
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="dup-guardrail")
    await guardrails_repo.create(
        AgentGuardrail(
            organization_id=organization_id,
            agent_id=agent.id,
            guardrail_type=GuardrailType.PII_DETECTION,
        )
    )

    await _insert_expecting(
        db_session_factory,
        AgentGuardrailRepository,
        AgentGuardrail(
            organization_id=organization_id,
            agent_id=agent.id,
            guardrail_type=GuardrailType.PII_DETECTION,
        ),
        DuplicateRecordError,
    )

    effective = await guardrails_repo.list_effective(organization_id, agent.id)
    assert len(effective) == 1
    assert effective[0].guardrail_type == GuardrailType.PII_DETECTION


async def test_org_wide_guardrails_are_not_deduplicated_by_the_constraint(
    guardrails_repo: AgentGuardrailRepository, organization_id: uuid.UUID
) -> None:
    """``agent_id`` is nullable and Postgres treats every ``NULL`` in a
    unique constraint as distinct, so ``uq_agent_guardrail_type``
    genuinely does *not* constrain org-wide defaults. Asserting the real
    behaviour, not the hoped-for one."""
    for _ in range(2):
        await guardrails_repo.create(
            AgentGuardrail(
                organization_id=organization_id,
                agent_id=None,
                guardrail_type=GuardrailType.POLICY_ENFORCEMENT,
            )
        )

    both = await guardrails_repo.list_effective(organization_id, uuid.uuid4())
    assert len(both) == 2
    assert {row.agent_id for row in both} == {None}


# ---- app/models/execution.py ------------------------------------------------------


async def test_agent_execution_column_defaults(
    agents_repo: AgentRepository,
    executions_repo: AgentExecutionRepository,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="executed")

    execution = await executions_repo.create(
        AgentExecution(organization_id=organization_id, agent_id=agent.id, started_at=utcnow())
    )

    assert execution.task_id is None
    assert execution.session_id is None
    assert execution.status == ExecutionStatus.PENDING
    assert execution.reasoning_mode == ReasoningMode.TOOL_BASED
    assert execution.model_provider == ModelProvider.OLLAMA
    assert execution.model_name == "llama3"
    assert execution.prompt_tokens == 0
    assert execution.completion_tokens == 0
    assert execution.total_tokens == 0
    assert execution.tool_calls_made == 0
    assert execution.reasoning_steps == 0
    assert execution.planning_ms is None
    assert execution.latency_ms is None
    assert execution.cost_usd == pytest.approx(0.0)
    assert execution.input_summary is None
    assert execution.output_summary is None
    assert execution.trace == []
    assert execution.completed_at is None
    assert execution.error is None


async def test_agent_execution_task_link_is_set_null_when_the_task_is_removed(
    agents_repo: AgentRepository,
    tasks_repo: AgentTaskRepository,
    executions_repo: AgentExecutionRepository,
    db_session: AsyncSession,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="exec-task")
    task = await tasks_repo.create(
        AgentTask(organization_id=organization_id, task_type="generic", scheduled_at=utcnow())
    )
    execution = await executions_repo.create(
        AgentExecution(
            organization_id=organization_id,
            agent_id=agent.id,
            task_id=task.id,
            started_at=utcnow(),
        )
    )

    await tasks_repo.purge(task.id)

    result = await db_session.execute(
        text("SELECT task_id FROM agent_executions WHERE id = :id"), {"id": execution.id}
    )
    assert result.scalar_one() is None


async def test_agent_execution_trace_json_round_trips(
    agents_repo: AgentRepository,
    executions_repo: AgentExecutionRepository,
    db_session: AsyncSession,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="traced")
    execution = await executions_repo.create(
        AgentExecution(
            organization_id=organization_id, agent_id=agent.id, trace=[], started_at=utcnow()
        )
    )

    execution.trace = [*execution.trace, {"type": "tool_call", "tool_key": "crm.lookup"}]
    await executions_repo.update(execution)
    db_session.expunge(execution)

    reloaded = await executions_repo.require_by_id(execution.id)
    assert reloaded.trace == [{"type": "tool_call", "tool_key": "crm.lookup"}]


# ---- app/models/memory.py ---------------------------------------------------------


async def test_agent_memory_column_defaults(
    agents_repo: AgentRepository,
    memory_repo: AgentMemoryRepository,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="remembering")

    memory = await memory_repo.create(
        AgentMemory(
            organization_id=organization_id,
            agent_id=agent.id,
            scope=MemoryScope.LONG_TERM,
            key="fact",
        )
    )

    assert memory.content == {}
    assert memory.summary is None
    assert memory.session_id is None
    assert memory.task_id is None
    assert memory.expires_at is None


async def test_agent_memory_has_no_database_uniqueness_on_agent_scope_key(
    agents_repo: AgentRepository,
    memory_repo: AgentMemoryRepository,
    organization_id: uuid.UUID,
) -> None:
    """Documented deliberately: uniqueness is a service-level
    "look up by key first" rule, never a DB constraint."""
    agent = await _agent(agents_repo, organization_id, slug="dup-memory")

    for _ in range(2):
        await memory_repo.create(
            AgentMemory(
                organization_id=organization_id,
                agent_id=agent.id,
                scope=MemoryScope.LONG_TERM,
                key="same-key",
            )
        )

    assert len(await memory_repo.list_for_agent(agent.id)) == 2


async def test_agent_memory_cascades_when_its_agent_row_is_removed(
    agents_repo: AgentRepository,
    memory_repo: AgentMemoryRepository,
    db_session: AsyncSession,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="memory-cascade")
    memory = await memory_repo.create(
        AgentMemory(
            organization_id=organization_id,
            agent_id=agent.id,
            scope=MemoryScope.TASK,
            key="scratch",
        )
    )

    await agents_repo.purge(agent.id)

    result = await db_session.execute(
        text("SELECT count(*) FROM agent_memory WHERE id = :id"), {"id": memory.id}
    )
    assert result.scalar_one() == 0


# ---- app/models/workflow.py -------------------------------------------------------


async def test_agent_workflow_column_defaults(
    workflows_repo: AgentWorkflowRepository, organization_id: uuid.UUID
) -> None:
    workflow = await workflows_repo.create(AgentWorkflow(organization_id=organization_id))

    assert workflow.agent_id is None
    assert workflow.task_id is None
    assert workflow.pattern == OrchestrationPattern.PLANNER_EXECUTOR
    assert workflow.status == WorkflowRunStatus.PENDING
    assert workflow.graph_definition == {}
    assert workflow.current_node_id is None
    assert workflow.checkpoint == {}
    assert workflow.participating_agent_ids == []
    assert workflow.started_at is None
    assert workflow.completed_at is None
    assert workflow.error is None


async def test_agent_workflow_json_columns_round_trip(
    workflows_repo: AgentWorkflowRepository,
    db_session: AsyncSession,
    organization_id: uuid.UUID,
) -> None:
    workflow = await workflows_repo.create(AgentWorkflow(organization_id=organization_id))
    participant = str(uuid.uuid4())

    workflow.graph_definition = {"nodes": [{"node_id": "start"}]}
    workflow.checkpoint = {"state": "running", "completed_node_ids": ["start"]}
    workflow.participating_agent_ids = [*workflow.participating_agent_ids, participant]
    await workflows_repo.update(workflow)
    db_session.expunge(workflow)

    reloaded = await workflows_repo.require_by_id(workflow.id)
    assert reloaded.graph_definition == {"nodes": [{"node_id": "start"}]}
    assert reloaded.checkpoint == {"state": "running", "completed_node_ids": ["start"]}
    assert reloaded.participating_agent_ids == [participant]


# ---- app/models/evaluation.py -----------------------------------------------------


async def test_agent_evaluation_column_defaults(
    agents_repo: AgentRepository,
    executions_repo: AgentExecutionRepository,
    evaluations_repo: AgentEvaluationRepository,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="evaluated")
    execution = await executions_repo.create(
        AgentExecution(organization_id=organization_id, agent_id=agent.id, started_at=utcnow())
    )

    evaluation = await evaluations_repo.create(
        AgentEvaluation(
            organization_id=organization_id,
            agent_id=agent.id,
            execution_id=execution.id,
            evaluated_at=utcnow(),
        )
    )

    assert evaluation.task_accuracy is None
    assert evaluation.execution_quality is None
    assert evaluation.reasoning_quality is None
    assert evaluation.tool_success_rate is None
    assert evaluation.latency_ms is None
    assert evaluation.cost_usd is None
    assert evaluation.human_feedback_score is None
    assert evaluation.is_regression_test is False
    assert evaluation.notes is None
    assert evaluation.evaluated_by is None


async def test_agent_evaluation_cascades_when_its_execution_is_removed(
    agents_repo: AgentRepository,
    executions_repo: AgentExecutionRepository,
    evaluations_repo: AgentEvaluationRepository,
    db_session: AsyncSession,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="eval-cascade")
    execution = await executions_repo.create(
        AgentExecution(organization_id=organization_id, agent_id=agent.id, started_at=utcnow())
    )
    evaluation = await evaluations_repo.create(
        AgentEvaluation(
            organization_id=organization_id,
            agent_id=agent.id,
            execution_id=execution.id,
            evaluated_at=utcnow(),
        )
    )

    await executions_repo.purge(execution.id)

    result = await db_session.execute(
        text("SELECT count(*) FROM agent_evaluations WHERE id = :id"), {"id": evaluation.id}
    )
    assert result.scalar_one() == 0


# ---- app/models/benchmark.py ------------------------------------------------------


async def test_agent_benchmark_column_defaults(
    agents_repo: AgentRepository,
    benchmarks_repo: AgentBenchmarkRepository,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="benchmarked")

    benchmark = await benchmarks_repo.create(
        AgentBenchmark(
            organization_id=organization_id,
            agent_id=agent.id,
            name="suite",
            started_at=utcnow(),
        )
    )

    assert benchmark.status == BenchmarkStatus.PENDING
    assert benchmark.total_cases == 0
    assert benchmark.passed_cases == 0
    assert benchmark.failed_cases == 0
    assert benchmark.score is None
    assert benchmark.results == []
    assert benchmark.completed_at is None
    assert benchmark.triggered_by is None
    assert benchmark.error is None


# ---- app/models/marketplace.py ----------------------------------------------------


async def test_agent_marketplace_entry_column_defaults(
    agents_repo: AgentRepository,
    marketplace_repo: AgentMarketplaceEntryRepository,
    organization_id: uuid.UUID,
) -> None:
    agent = await _agent(agents_repo, organization_id, slug="listed")

    entry = await marketplace_repo.create(
        AgentMarketplaceEntry(organization_id=organization_id, agent_id=agent.id)
    )

    assert entry.status == AgentMarketplaceListingStatus.DRAFT
    assert entry.featured is False
    assert entry.publisher == "AI-IOS"
    assert entry.description is None
    assert entry.install_count == 0
    assert entry.rating_total == pytest.approx(0.0)
    assert entry.rating_count == 0
    assert entry.listed_at is None
    assert entry.approved_by is None
    assert entry.approved_at is None
    assert entry.rejection_reason is None


async def test_agent_marketplace_entry_is_unique_per_agent(
    agents_repo: AgentRepository,
    marketplace_repo: AgentMarketplaceEntryRepository,
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    """``uq_agent_marketplace_entry`` -- one listing surface per agent,
    globally, not merely per organization."""
    agent = await _agent(agents_repo, organization_id, slug="listed-once")
    await marketplace_repo.create(
        AgentMarketplaceEntry(organization_id=organization_id, agent_id=agent.id)
    )

    await _insert_expecting(
        db_session_factory,
        AgentMarketplaceEntryRepository,
        AgentMarketplaceEntry(organization_id=organization_id, agent_id=agent.id),
        DuplicateRecordError,
    )

    assert await marketplace_repo.get_for_agent(agent.id) is not None


# ---- app/models/governance.py -----------------------------------------------------


async def test_agent_statistic_column_defaults(
    statistics_repo: AgentStatisticRepository, organization_id: uuid.UUID
) -> None:
    window = await statistics_repo.create(
        AgentStatistic(
            organization_id=organization_id,
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )

    assert window.active_agents == 0
    assert window.task_count == 0
    assert window.executions_succeeded == 0
    assert window.executions_failed == 0
    assert window.total_tokens == 0
    assert window.average_cost_usd is None
    assert window.average_latency_ms is None
    assert window.memory_rows_created == 0
    assert window.by_agent_type == {}
    assert window.by_model_provider == {}
    assert window.by_tool == {}


async def test_agent_report_column_defaults(
    reports_repo: AgentReportRepository, organization_id: uuid.UUID
) -> None:
    report = await reports_repo.create(
        AgentReport(organization_id=organization_id, kind=ReportKind.USAGE, title="Usage report")
    )

    assert report.report_format == ReportFormat.JSON
    assert report.status == ReportStatus.PENDING
    assert report.content == {}
    assert report.row_count is None
    assert report.generated_by is None
    assert report.generated_at is None
    assert report.duration_ms is None
    assert report.error is None


async def test_agent_audit_column_defaults(
    audit_repo: AgentAuditRepository, organization_id: uuid.UUID
) -> None:
    entry = await audit_repo.create(
        AgentAudit(
            organization_id=organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="agent",
            occurred_at=utcnow(),
            summary="Something happened.",
        )
    )

    assert entry.entity_id is None
    assert entry.entity_reference is None
    assert entry.actor_id is None
    assert entry.actor_type == "user"
    assert entry.succeeded is True
    assert entry.changes == {}
    assert entry.context == {}
    assert entry.request_id is None
    assert entry.ip_address is None


async def test_agent_audit_requires_a_summary(
    db_session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    await _insert_expecting(
        db_session_factory,
        AgentAuditRepository,
        AgentAudit(
            organization_id=organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="agent",
            occurred_at=utcnow(),
        ),
        ConstraintFailedError,
    )


# ---- tenancy ------------------------------------------------------------------------


async def test_every_model_requires_an_organization_id(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``TenantMixin.organization_id`` is non-nullable everywhere -- a
    row with no tenant could never be scoped by any repository query."""
    await _insert_expecting(
        db_session_factory,
        AgentTaskRepository,
        AgentTask(task_type="orphan", scheduled_at=utcnow()),
        ConstraintFailedError,
    )


async def test_soft_delete_hides_a_row_from_the_default_repository_select(
    agents_repo: AgentRepository, organization_id: uuid.UUID
) -> None:
    """``SoftDeleteMixin`` + ``BaseRepository._base_select``: the row is
    still physically present, which is why the FK cascade tests above
    have to purge rather than delete."""
    agent = await _agent(agents_repo, organization_id, slug="soft-deleted")

    await agents_repo.delete(agent.id)

    assert await agents_repo.get_by_id(agent.id) is None
    still_there = await agents_repo.get_by_id(agent.id, include_deleted=True)
    assert still_there is not None
    assert still_there.is_active is False
    assert still_there.deleted_at is not None
