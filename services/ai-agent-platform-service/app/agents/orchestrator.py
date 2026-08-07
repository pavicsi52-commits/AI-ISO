"""Multi-agent orchestration base (docs/060 "MULTI-AGENT ORCHESTRATION":
Task Decomposition, Agent Routing/Dynamic Agent Selection, Result
Aggregation).

Mirrors ``ai-assistant-service``'s own ``app/agents/orchestrator.py``
(Prompt 046) ``AgentOrchestrator``/``AgentTask``/``AgentResult``/
``SharedMemory``/``route``/``decompose``/``aggregate`` shape closely --
rewritten here, not imported. The six *additional* named coordination
patterns docs/060 requires beyond sequential/parallel (Hierarchical,
Peer-to-peer, Supervisor, Planner/Executor, Delegation, Conflict
Resolution) build on top of this module's own :meth:`AgentOrchestrator
.run_one` and live in :mod:`app.agents.patterns`.

**Two real differences from the mirrored precedent**, both forced by
this service's own schema:

- An :class:`~app.models.agent.Agent` row carries identity and type,
  never its own model/prompt configuration -- that lives on a separate
  :class:`~app.models.profile.AgentProfile` row. Every dispatch needs
  both.
- Routing resolves to potentially **several** agents of a matching
  type, not one -- so this module also implements "Dynamic Agent
  Selection" for real: :func:`select_dynamically` picks the healthiest
  candidate (fewest consecutive failures, most recently active) from
  live data, rather than the precedent's own fixed one-agent-per-type
  map.

**Parallelism is real but bounded, and deliberately I/O-only** -- each
agent call is a network request to a model provider, safe to overlap
under a semaphore; nothing here touches the database concurrently.

**Failure recovery**: one failing agent does not abort the run. Its
task is recorded as failed with its own error and the remaining
results are still aggregated, because a partial answer with an honest
gap is more useful than no answer at all.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from shared_core.exceptions.ai import AIError
from shared_core.logging.logger import get_logger

from app.clients.base import ChatMessage
from app.clients.registry import ModelRegistry
from app.models.agent import Agent
from app.models.enums import AgentType, ModelProvider, RoutingStrategy
from app.models.profile import AgentProfile

logger = get_logger("app.agents.orchestrator")

_KEYWORD_ROUTING: tuple[tuple[AgentType, tuple[str, ...]], ...] = (
    (AgentType.MONITORING, ("metric", "alert", "cpu", "memory", "latency", "capacity", "health")),
    (AgentType.AUTOMATION, ("automation", "playbook", "job", "run ", "execute", "remediate")),
    (AgentType.INFRASTRUCTURE, ("server", "host", "node", "topology", "cluster", "network")),
    (AgentType.COMPLIANCE, ("compliance", "regulation", "audit", "standard", "control")),
    (AgentType.SECURITY, ("security", "vulnerability", "permission", "credential", "cve")),
    (AgentType.REPORTING, ("report", "summary", "summarise", "summarize", "dashboard")),
    (
        AgentType.KNOWLEDGE_GRAPH,
        ("graph", "relationship", "runbook", "wiki", "how do i", "what is"),
    ),
    (AgentType.VALIDATOR, ("validate", "validation", "conformance", "verify")),
    (AgentType.REVIEWER, ("review", "approve", "critique", "assess")),
    (AgentType.RESEARCHER, ("research", "investigate", "look up", "gather", "find out")),
    (AgentType.PLANNER, ("plan", "strategy", "roadmap", "decompose", "break down")),
    (AgentType.COORDINATOR, ("coordinate", "delegate", "assign", "orchestrate")),
)
"""Keyword routing table ("Agent Routing").

Deliberately explicit and inspectable rather than asking a model which
agent to use, mirroring the precedent's own reasoning: routing is
cheap, frequent, and must be predictable. Anything unmatched falls to
the executor agent type. ``CUSTOM`` has no keywords -- it is an open
extension point, never a routing target.

Table *order* carries no meaning; see :func:`route` for why the longest
matched keyword wins instead.
"""


@dataclass(frozen=True, slots=True)
class AgentTask:
    """One unit of work assigned to an agent type."""

    description: str
    agent_type: AgentType
    context: str = ""


@dataclass(frozen=True, slots=True)
class AgentResult:
    """What one agent produced for its own task."""

    task: AgentTask
    agent_name: str
    content: str
    succeeded: bool
    error: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(slots=True)
class SharedMemory:
    """Scratch space agents in one run share ("Shared Memory").

    Plain in-run state, not persisted: it exists so a later task can
    see an earlier one's finding within the same request, which is what
    sequential decomposition needs.
    """

    facts: dict[str, str] = field(default_factory=dict)

    def record(self, key: str, value: str) -> None:
        """Record one fact for later tasks in this run."""
        self.facts[key] = value

    def as_context(self) -> str:
        """Render accumulated facts as context, or ``""`` if none."""
        if not self.facts:
            return ""
        lines = [f"- {key}: {value}" for key, value in self.facts.items()]
        return "Findings from earlier steps:\n" + "\n".join(lines)


def route(description: str) -> AgentType:
    """Pick the agent type best suited to *description*.

    The **longest matched keyword wins**, not the first table entry --
    keyword length is a good proxy for specificity. Unmatched falls to
    :attr:`AgentType.EXECUTOR`, the general-purpose fallback.
    """
    lowered = description.lower()
    best_type = AgentType.EXECUTOR
    best_length = 0
    for agent_type, keywords in _KEYWORD_ROUTING:
        for keyword in keywords:
            if keyword in lowered and len(keyword) > best_length:
                best_type = agent_type
                best_length = len(keyword)
    return best_type


def decompose(request: str, *, max_tasks: int = 4) -> list[AgentTask]:
    """Split a request into routed tasks ("Task Decomposition").

    Splits on explicit conjunctions and sentence boundaries rather than
    asking a model to plan, for the same reason routing is explicit: it
    is deterministic, free, and inspectable. A request with no clear
    split becomes a single task, which is the common case and stays
    cheap.
    """
    text = request.strip()
    if not text:
        return []

    fragments: list[str] = []
    for sentence in text.replace("?", ".").replace("!", ".").split("."):
        cleaned = sentence.strip()
        if not cleaned:
            continue
        for part in cleaned.split(" and then "):
            piece = part.strip()
            if piece:
                fragments.append(piece)

    if not fragments:
        fragments = [text]
    return [
        AgentTask(description=fragment, agent_type=route(fragment))
        for fragment in fragments[:max_tasks]
    ]


def select_dynamically(candidates: Sequence[Agent]) -> Agent | None:
    """ "Dynamic Agent Selection" -- among agents of a matching type,
    pick the healthiest one from live data: fewest consecutive
    failures first, most recently active as the tiebreak.

    A genuine gap beyond static keyword :func:`route`, which only ever
    picks a *type* -- this picks the specific *instance* of that type
    best positioned to succeed right now.
    """
    if not candidates:
        return None

    def _key(agent: Agent) -> tuple[int, float]:
        last_active = agent.last_executed_at or datetime.min.replace(tzinfo=UTC)
        return (agent.consecutive_failures, -last_active.timestamp())

    return min(candidates, key=_key)


class AgentOrchestrator:
    """Runs agents over decomposed tasks and aggregates their results."""

    def __init__(
        self,
        registry: ModelRegistry,
        agents_by_type: dict[AgentType, list[Agent]],
        profiles_by_agent_id: dict[UUID, AgentProfile],
        *,
        max_parallel_agents: int = 5,
    ) -> None:
        self._registry = registry
        self._agents = agents_by_type
        self._profiles = profiles_by_agent_id
        self._max_parallel_agents = max_parallel_agents

    def agent_for(self, task: AgentTask) -> Agent | None:
        """Resolve a task's own agent instance, falling back to the
        executor type, via "Dynamic Agent Selection"."""
        candidates = self._agents.get(task.agent_type) or self._agents.get(AgentType.EXECUTOR) or []
        return select_dynamically(candidates)

    async def run_one(self, task: AgentTask, shared: SharedMemory) -> AgentResult:
        """Run one task through its own resolved agent, never raising."""
        agent = self.agent_for(task)
        if agent is None:
            return AgentResult(
                task=task,
                agent_name="unassigned",
                content="",
                succeeded=False,
                error=f"No agent registered for {task.agent_type!s} and no executor agent.",
            )
        profile = self._profiles.get(agent.id)
        if profile is None:
            return AgentResult(
                task=task,
                agent_name=agent.name,
                content="",
                succeeded=False,
                error=f"Agent {agent.name!r} has no configuration profile.",
            )

        prompt_parts = [part for part in (shared.as_context(), task.context) if part]
        prompt_parts.append(task.description)
        messages = []
        if profile.system_prompt:
            messages.append(ChatMessage(role="system", content=profile.system_prompt))
        messages.append(ChatMessage(role="user", content="\n\n".join(prompt_parts)))

        provider = profile.model_provider
        if not isinstance(provider, ModelProvider):
            provider = ModelProvider(provider)
        strategy = profile.routing_strategy
        if not isinstance(strategy, RoutingStrategy):
            strategy = RoutingStrategy(strategy)

        try:
            completion = await self._registry.chat(
                messages,
                strategy=strategy,
                provider=provider,
                model=profile.model_name,
                temperature=profile.temperature,
                max_tokens=profile.max_tokens,
            )
        except AIError as exc:
            logger.warning(
                "Agent task failed.",
                extra={"extra_fields": {"agent": agent.name, "error": str(exc)}},
            )
            return AgentResult(
                task=task, agent_name=agent.name, content="", succeeded=False, error=str(exc)
            )

        return AgentResult(
            task=task,
            agent_name=agent.name,
            content=completion.content,
            succeeded=True,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
        )

    async def run_sequential(self, tasks: list[AgentTask]) -> list[AgentResult]:
        """Run tasks in order, each seeing earlier findings."""
        shared = SharedMemory()
        results: list[AgentResult] = []
        for task in tasks:
            result = await self.run_one(task, shared)
            results.append(result)
            if result.succeeded and result.content:
                shared.record(task.description[:60], result.content)
        return results

    async def run_parallel(self, tasks: list[AgentTask]) -> list[AgentResult]:
        """Run independent tasks concurrently, bounded by a semaphore.

        Safe to overlap because each call is provider I/O and touches
        no database session. Tasks cannot see each other's findings --
        that is the trade for the latency win, and why
        :meth:`run_sequential` exists for dependent work.
        """
        if not tasks:
            return []
        semaphore = asyncio.Semaphore(self._max_parallel_agents)
        shared = SharedMemory()

        async def _bounded(task: AgentTask) -> AgentResult:
            async with semaphore:
                return await self.run_one(task, shared)

        return list(await asyncio.gather(*(_bounded(task) for task in tasks)))


def aggregate(results: list[AgentResult]) -> str:
    """Combine agent results into one answer ("Result Aggregation").

    Failures are reported inline rather than dropped: a caller reading
    "I could not check monitoring because the provider was
    unreachable" is far better served than one silently given a
    partial answer that looks complete.
    """
    if not results:
        return ""
    if len(results) == 1 and results[0].succeeded:
        return results[0].content

    sections: list[str] = []
    for result in results:
        if result.succeeded:
            sections.append(result.content)
        else:
            sections.append(
                f"[Could not complete '{result.task.description}': "
                f"{result.error or 'unknown error'}]"
            )
    return "\n\n".join(section for section in sections if section)


__all__ = [
    "AgentOrchestrator",
    "AgentResult",
    "AgentTask",
    "SharedMemory",
    "aggregate",
    "decompose",
    "route",
    "select_dynamically",
]
