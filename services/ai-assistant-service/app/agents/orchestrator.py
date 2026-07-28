"""Multi-agent orchestration ("MULTI AGENT ORCHESTRATION").

A planner decomposes a request into tasks, each task is routed to the
agent whose type fits it, tasks run sequentially or in parallel, and
their results are aggregated.

**Parallelism is real but bounded, and deliberately I/O-only.**
Agents that can run concurrently do so under a semaphore
(``max_parallel_agents``); each agent call is a network request to a
model provider, which is genuinely safe to overlap. Nothing here
touches the database concurrently -- persistence happens in the calling
orchestrator, sequentially, for the same reason every AI-IOS service
since ``services/validation-service`` does it that way: an
``AsyncSession`` is not safe for concurrent use even for reads.

**Failure recovery**: one failing agent does not abort the run. Its
task is recorded as failed with its own error and the remaining
results are still aggregated, because a partial answer with an honest
gap is more useful than no answer at all.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from shared_core.exceptions.ai import AIError
from shared_core.logging.logger import get_logger

from app.clients.base import ChatMessage
from app.clients.registry import ModelRegistry
from app.models.ai_agent import AiAgent
from app.models.enums import AgentType, MessageRole, ModelProvider

logger = get_logger("app.agents.orchestrator")

_KEYWORD_ROUTING: tuple[tuple[AgentType, tuple[str, ...]], ...] = (
    (AgentType.MONITORING, ("metric", "alert", "cpu", "memory", "latency", "capacity", "health")),
    (AgentType.VALIDATION, ("validate", "validation", "compliance", "check", "conformance")),
    (AgentType.AUTOMATION, ("automation", "playbook", "job", "run ", "execute", "remediate")),
    (AgentType.WORKFLOW, ("workflow", "pipeline", "orchestration", "approval")),
    (AgentType.CONFIGURATION, ("config", "drift", "baseline", "setting", "parameter")),
    (AgentType.INFRASTRUCTURE, ("server", "host", "node", "topology", "cluster", "network")),
    (AgentType.SECURITY, ("security", "vulnerability", "permission", "credential", "cve")),
    (AgentType.REPORTING, ("report", "summary", "summarise", "summarize", "dashboard")),
    (AgentType.KNOWLEDGE, ("document", "runbook", "wiki", "policy", "how do i", "what is")),
)
"""Keyword routing table ("Agent Routing").

Deliberately explicit and inspectable rather than asking a model which
agent to use: routing is cheap, frequent, and must be predictable --
spending a model call to pick a model call would double latency and
make the choice non-reproducible. Anything unmatched falls to the
reasoning agent.

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

    The **longest matched keyword wins**, not the first table entry.
    Keyword length is a good proxy for specificity, and first-match
    ordering gets this wrong in practice: "check for vulnerability
    exposure" contains both the generic ``"check"`` (validation) and
    the highly specific ``"vulnerability"`` (security), and should
    clearly route to security. Ties break on table order, so the
    behaviour stays deterministic.
    """
    lowered = description.lower()
    best_type = AgentType.REASONING
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
    asking a model to plan, for the same reason routing is explicit:
    it is deterministic, free, and inspectable. A request with no clear
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


class AgentOrchestrator:
    """Runs agents over decomposed tasks and aggregates their results."""

    def __init__(
        self,
        registry: ModelRegistry,
        agents_by_type: dict[AgentType, AiAgent],
        *,
        max_parallel_agents: int = 5,
    ) -> None:
        self._registry = registry
        self._agents = agents_by_type
        self._max_parallel_agents = max_parallel_agents

    def _agent_for(self, task: AgentTask) -> AiAgent | None:
        """Resolve a task's own agent, falling back to the reasoning agent."""
        return self._agents.get(task.agent_type) or self._agents.get(AgentType.REASONING)

    async def _run_one(self, task: AgentTask, shared: SharedMemory) -> AgentResult:
        """Run one task through its agent, never raising."""
        agent = self._agent_for(task)
        if agent is None:
            return AgentResult(
                task=task,
                agent_name="unassigned",
                content="",
                succeeded=False,
                error=f"No agent registered for {str(task.agent_type)!r} and no reasoning agent.",
            )

        prompt_parts = [part for part in (shared.as_context(), task.context) if part]
        prompt_parts.append(task.description)
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=agent.system_prompt or ""),
            ChatMessage(role=MessageRole.USER, content="\n\n".join(prompt_parts)),
        ]
        if not agent.system_prompt:
            messages = messages[1:]

        try:
            completion = await self._registry.chat_with_fallback(
                messages,
                provider=(
                    agent.provider
                    if isinstance(agent.provider, ModelProvider)
                    else ModelProvider(agent.provider)
                ),
                model=agent.model,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
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
            result = await self._run_one(task, shared)
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
                return await self._run_one(task, shared)

        return list(await asyncio.gather(*(_bounded(task) for task in tasks)))


def aggregate(results: list[AgentResult]) -> str:
    """Combine agent results into one answer ("Result Aggregation").

    Failures are reported inline rather than dropped: a user reading
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
]
