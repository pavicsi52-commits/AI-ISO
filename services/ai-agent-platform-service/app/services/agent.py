"""Agent lifecycle (docs/060 "AGENT LIFECYCLE": Registration,
Configuration, Versioning, Activation, Deactivation, Health Monitoring,
Retirement; backs ``GET/POST /agents``, ``GET/PUT/DELETE /agents/{id}``,
``POST /agents/{id}/pause``, ``POST /agents/{id}/resume``).

Registering an agent creates its :class:`~app.models.agent.Agent` row,
own initial :class:`~app.models.profile.AgentProfile`, and first
:class:`~app.models.agent.AgentVersion` snapshot together -- an agent
with no profile cannot actually run, so there is no useful
intermediate state where one exists without the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.events.agent_events import AgentRegisteredEvent
from app.models.agent import Agent, AgentVersion
from app.models.enums import (
    AgentLifecycleStatus,
    AgentType,
    AuditAction,
    ModelProvider,
    ReasoningMode,
    RoutingStrategy,
)
from app.models.governance import AgentAudit
from app.models.profile import AgentProfile
from app.repositories.agent import AgentRepository, AgentVersionRepository
from app.repositories.governance import AgentAuditRepository
from app.repositories.profile import AgentProfileRepository
from app.types import EventPublisher

_INITIAL_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class ProfileFields:
    """The subset of :class:`AgentProfile` a caller supplies at
    registration or reconfiguration time."""

    system_prompt: str | None = None
    model_provider: ModelProvider = ModelProvider.OLLAMA
    model_name: str = "llama3"
    temperature: float = 0.2
    max_tokens: int = 2_048
    reasoning_mode: ReasoningMode = ReasoningMode.TOOL_BASED
    routing_strategy: RoutingStrategy = RoutingStrategy.FALLBACK
    fallback_providers: list[str] = field(default_factory=list)
    allowed_tool_keys: list[str] = field(default_factory=list)
    max_reasoning_steps: int = 8
    extra_config: dict[str, Any] = field(default_factory=dict)

    def to_snapshot(self) -> dict[str, Any]:
        """Render as a plain dict for ``AgentVersion.profile_snapshot``."""
        return {
            "system_prompt": self.system_prompt,
            "model_provider": str(self.model_provider),
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "reasoning_mode": str(self.reasoning_mode),
            "routing_strategy": str(self.routing_strategy),
            "fallback_providers": list(self.fallback_providers),
            "allowed_tool_keys": list(self.allowed_tool_keys),
            "max_reasoning_steps": self.max_reasoning_steps,
            "extra_config": dict(self.extra_config),
        }


class AgentService:
    """Registers, configures, and transitions one agent's own lifecycle."""

    def __init__(
        self,
        agents: AgentRepository,
        profiles: AgentProfileRepository,
        versions: AgentVersionRepository,
        audit: AgentAuditRepository,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._agents = agents
        self._profiles = profiles
        self._versions = versions
        self._audit = audit
        self._publish_event = publish_event

    async def register(
        self,
        *,
        organization_id: UUID,
        slug: str,
        name: str,
        agent_type: AgentType,
        description: str | None = None,
        owner_id: str | None = None,
        tags: list[str] | None = None,
        profile: ProfileFields,
        registered_by: str | None = None,
    ) -> Agent:
        """Register a new agent, its own initial profile, and first
        version snapshot, activating it immediately.

        Raises:
            ConflictError: If *slug* is already registered in
                *organization_id*.
        """
        if await self._agents.get_by_slug(organization_id, slug) is not None:
            raise ConflictError(f"Agent slug {slug!r} is already registered in this organization.")

        agent = await self._agents.create(
            Agent(
                organization_id=organization_id,
                slug=slug,
                name=name,
                description=description,
                agent_type=agent_type,
                status=AgentLifecycleStatus.ACTIVE,
                current_version_number=_INITIAL_VERSION,
                tags=list(tags or []),
                owner_id=owner_id,
                consecutive_failures=0,
            )
        )
        await self._profiles.create(
            AgentProfile(
                organization_id=organization_id,
                agent_id=agent.id,
                system_prompt=profile.system_prompt,
                model_provider=profile.model_provider,
                model_name=profile.model_name,
                temperature=profile.temperature,
                max_tokens=profile.max_tokens,
                reasoning_mode=profile.reasoning_mode,
                routing_strategy=profile.routing_strategy,
                fallback_providers=list(profile.fallback_providers),
                allowed_tool_keys=list(profile.allowed_tool_keys),
                max_reasoning_steps=profile.max_reasoning_steps,
                extra_config=dict(profile.extra_config),
            )
        )
        await self._versions.create(
            AgentVersion(
                organization_id=organization_id,
                agent_id=agent.id,
                version_number=_INITIAL_VERSION,
                profile_snapshot=profile.to_snapshot(),
                is_current=True,
                released_at=datetime.now(UTC),
                released_by=registered_by,
            )
        )
        await self._audit.create(
            AgentAudit(
                organization_id=organization_id,
                action=AuditAction.AGENT_REGISTERED,
                entity_type="agent",
                entity_id=agent.id,
                entity_reference=agent.slug,
                actor_id=registered_by,
                occurred_at=datetime.now(UTC),
                summary=f"Agent {agent.slug!r} registered and activated.",
            )
        )
        await self._publish_event(
            AgentRegisteredEvent(
                source_service="ai-agent-platform-service",
                organization_id=organization_id,
                payload={"agent_id": str(agent.id), "slug": agent.slug},
            )
        )
        return agent

    async def update(
        self,
        agent: Agent,
        *,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        owner_id: str | None = None,
    ) -> Agent:
        """Update *agent*'s own identity fields. ``None`` leaves a
        field unchanged."""
        if name is not None:
            agent.name = name
        if description is not None:
            agent.description = description
        if tags is not None:
            agent.tags = list(tags)
        if owner_id is not None:
            agent.owner_id = owner_id
        return await self._agents.update(agent)

    async def pause(self, agent: Agent) -> Agent:
        """Pause an active agent so it stops being dispatched.

        Raises:
            ConflictError: If *agent* isn't currently ``ACTIVE``.
        """
        if agent.status != AgentLifecycleStatus.ACTIVE:
            raise ConflictError(
                f"Agent {agent.slug!r} is {agent.status!s}, not active; cannot pause."
            )
        agent.status = AgentLifecycleStatus.PAUSED
        return await self._agents.update(agent)

    async def resume(self, agent: Agent) -> Agent:
        """Resume a paused agent.

        Raises:
            ConflictError: If *agent* isn't currently ``PAUSED``.
        """
        if agent.status != AgentLifecycleStatus.PAUSED:
            raise ConflictError(
                f"Agent {agent.slug!r} is {agent.status!s}, not paused; cannot resume."
            )
        agent.status = AgentLifecycleStatus.ACTIVE
        return await self._agents.update(agent)

    async def retire(self, agent: Agent, *, retired_by: str | None = None) -> Agent:
        """Retire an agent permanently (a terminal status, plus the
        usual soft delete)."""
        agent.status = AgentLifecycleStatus.RETIRED
        agent = await self._agents.update(agent)
        await self._audit.create(
            AgentAudit(
                organization_id=agent.organization_id,
                action=AuditAction.AGENT_RETIRED,
                entity_type="agent",
                entity_id=agent.id,
                entity_reference=agent.slug,
                actor_id=retired_by,
                occurred_at=datetime.now(UTC),
                summary=f"Agent {agent.slug!r} retired.",
            )
        )
        await self._agents.delete(agent.id)
        return agent


__all__ = ["AgentService", "ProfileFields"]
