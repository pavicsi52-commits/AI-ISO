"""Runs one agent against one request, end to end (docs/060's own
"AGENT LIFECYCLE" > Execution stage; backs ``POST /agents/{id}/execute``).

The one place every reasoning mode, the memory service, both input/
output guardrails, and (for ``TOOL_BASED``) the full tool-execution
stack meet -- everything else in this service is a primitive this
class composes, never re-implements.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from shared_core.exceptions.ai import AIError
from shared_core.exceptions.conflict import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.automation_client import AutomationClient
from app.clients.base import ChatMessage
from app.clients.dispatch import dispatch_chat
from app.clients.registry import ModelRegistry
from app.events.agent_events import AgentCompletedEvent, AgentFailedEvent
from app.graph.client import GraphClient
from app.guardrails.engine import screen_model_output, screen_user_input
from app.memory.service import MemoryService
from app.models.agent import Agent
from app.models.enums import AgentLifecycleStatus, ExecutionStatus, ReasoningMode
from app.models.execution import AgentExecution
from app.reasoning.engine import (
    ReasoningResult,
    run_hybrid,
    run_knowledge_graph,
    run_plan_and_execute,
    run_reflection,
    run_self_verification,
    run_tool_based,
    run_tree_of_thought,
)
from app.repositories.agent import AgentRepository
from app.repositories.execution import AgentExecutionRepository
from app.repositories.permission import AgentPermissionGrantRepository
from app.repositories.profile import AgentProfileRepository
from app.repositories.tool import AgentToolRepository
from app.sandbox.policy import AgentSandboxPolicy
from app.services.tool_handlers import build_handler_registry
from app.tool_execution.executor import ToolExecutor
from app.types import EventPublisher

_INPUT_SUMMARY_LIMIT = 2_000
_OUTPUT_SUMMARY_LIMIT = 2_000


class ExecutionService:
    """Executes one agent run through its own configured reasoning mode."""

    def __init__(
        self,
        agents: AgentRepository,
        profiles: AgentProfileRepository,
        tools: AgentToolRepository,
        permissions: AgentPermissionGrantRepository,
        executions: AgentExecutionRepository,
        memory: MemoryService,
        registry: ModelRegistry,
        *,
        http_client: httpx.AsyncClient,
        sandbox_policy: AgentSandboxPolicy,
        graph_client: GraphClient | None,
        automation_service_base_url: str,
        session: AsyncSession | None = None,
        publish_event: EventPublisher,
    ) -> None:
        self._agents = agents
        self._profiles = profiles
        self._tools = tools
        self._permissions = permissions
        self._executions = executions
        self._memory = memory
        self._registry = registry
        self._http_client = http_client
        self._sandbox_policy = sandbox_policy
        self._graph_client = graph_client
        self._automation_service_base_url = automation_service_base_url
        self._session = session
        self._publish_event = publish_event

    async def execute_agent(
        self,
        agent: Agent,
        *,
        request: str,
        session_id: UUID | None = None,
        task_id: UUID | None = None,
        caller_token: str = "",
        allow_mutating: bool = False,
    ) -> AgentExecution:
        """Run *agent* against *request*, recording a full
        :class:`AgentExecution`.

        Raises:
            ConflictError: If *agent* isn't currently ``ACTIVE``.
        """
        if agent.status != AgentLifecycleStatus.ACTIVE:
            raise ConflictError(f"Agent {agent.slug!r} is {agent.status!s}, not active.")
        profile = await self._profiles.require_for_agent(agent.id)

        execution = await self._executions.create(
            AgentExecution(
                organization_id=agent.organization_id,
                agent_id=agent.id,
                task_id=task_id,
                session_id=session_id,
                status=ExecutionStatus.RUNNING,
                reasoning_mode=profile.reasoning_mode,
                model_provider=profile.model_provider,
                model_name=profile.model_name,
                input_summary=request[:_INPUT_SUMMARY_LIMIT],
                trace=[],
                started_at=datetime.now(UTC),
            )
        )

        screened_input = screen_user_input(request)
        if screened_input.is_blocked:
            return await self._fail(
                execution,
                agent,
                error=f"Blocked by guardrails: {'; '.join(screened_input.findings)}",
            )

        memory_context = await self._memory.as_system_context(
            agent.id, session_id=session_id, task_id=task_id
        )
        full_request = f"{memory_context}\n\n{request}" if memory_context else request

        started = time.perf_counter()
        try:
            content, execution = await self._dispatch_reasoning(
                agent,
                profile,
                execution,
                request=full_request,
                caller_token=caller_token,
                allow_mutating=allow_mutating,
            )
        except AIError as exc:
            return await self._fail(execution, agent, error=str(exc))

        screened_output = screen_model_output(content)

        execution.output_summary = screened_output.text[:_OUTPUT_SUMMARY_LIMIT]
        execution.latency_ms = (time.perf_counter() - started) * 1_000
        execution.status = ExecutionStatus.COMPLETED
        execution.completed_at = datetime.now(UTC)
        execution = await self._executions.update(execution)

        agent.last_executed_at = datetime.now(UTC)
        agent.consecutive_failures = 0
        await self._agents.update(agent)

        await self._publish_event(
            AgentCompletedEvent(
                source_service="ai-agent-platform-service",
                organization_id=agent.organization_id,
                payload={"agent_id": str(agent.id), "execution_id": str(execution.id)},
            )
        )
        return execution

    async def _fail(self, execution: AgentExecution, agent: Agent, *, error: str) -> AgentExecution:
        execution.status = ExecutionStatus.FAILED
        execution.error = error
        execution.completed_at = datetime.now(UTC)
        execution = await self._executions.update(execution)

        agent.consecutive_failures += 1
        await self._agents.update(agent)

        await self._publish_event(
            AgentFailedEvent(
                source_service="ai-agent-platform-service",
                organization_id=agent.organization_id,
                payload={
                    "agent_id": str(agent.id),
                    "execution_id": str(execution.id),
                    "error": error,
                },
            )
        )
        return execution

    async def _dispatch_reasoning(
        self,
        agent: Agent,
        profile,
        execution: AgentExecution,
        *,
        request: str,
        caller_token: str,
        allow_mutating: bool,
    ) -> tuple[str, AgentExecution]:
        """Route to the configured reasoning mode and fold its own
        trace/token counters back onto *execution*.

        Raises:
            AIError: If the underlying reasoning run failed.
        """
        mode = profile.reasoning_mode
        if not isinstance(mode, ReasoningMode):
            mode = ReasoningMode(mode)

        if mode is ReasoningMode.TOOL_BASED:
            result = await self._run_tool_based(
                agent,
                profile,
                execution,
                request=request,
                caller_token=caller_token,
                allow_mutating=allow_mutating,
            )
        elif mode is ReasoningMode.TREE_OF_THOUGHT:
            result = await run_tree_of_thought(self._registry, profile, request)
        elif mode is ReasoningMode.PLAN_AND_EXECUTE:
            result = await run_plan_and_execute(
                self._registry, profile, request, max_steps=profile.max_reasoning_steps
            )
        elif mode is ReasoningMode.REFLECTION:
            result = await run_reflection(self._registry, profile, request)
        elif mode is ReasoningMode.SELF_VERIFICATION:
            result = await run_self_verification(self._registry, profile, request)
        elif mode is ReasoningMode.KNOWLEDGE_GRAPH:
            if self._graph_client is None:
                raise AIError("Knowledge Graph reasoning requires a configured graph client.")
            result = await run_knowledge_graph(
                self._registry, profile, request, graph=self._graph_client
            )
        elif mode is ReasoningMode.HYBRID:
            result = await run_hybrid(
                self._registry, profile, request, max_steps=profile.max_reasoning_steps
            )
        else:
            # CHAIN_OF_THOUGHT -- "internal only" per docs/060: a single plain
            # call, never a separate multi-step loop.
            completion = await dispatch_chat(
                self._registry, profile, [ChatMessage(role="user", content=request)]
            )
            result = ReasoningResult(
                content=completion.content,
                prompt_tokens=completion.prompt_tokens,
                completion_tokens=completion.completion_tokens,
            )

        execution.trace = [*execution.trace, *result.steps]
        execution.prompt_tokens += result.prompt_tokens
        execution.completion_tokens += result.completion_tokens
        execution.total_tokens = execution.prompt_tokens + execution.completion_tokens
        execution.reasoning_steps = len(result.steps)

        if not result.succeeded:
            raise AIError(result.error or "Reasoning failed with no further detail.")
        return result.content, execution

    async def _run_tool_based(
        self,
        agent: Agent,
        profile,
        execution: AgentExecution,
        *,
        request: str,
        caller_token: str,
        allow_mutating: bool,
    ) -> ReasoningResult:
        tools = await self._tools.list_enabled(agent.organization_id)
        granted = [grant.category for grant in await self._permissions.list_granted(agent.id)]
        automation_client = (
            AutomationClient(
                self._http_client,
                base_url=self._automation_service_base_url,
                caller_token=caller_token,
            )
            if caller_token
            else None
        )
        handlers = build_handler_registry(
            tools,
            http_client=self._http_client,
            sandbox_policy=self._sandbox_policy,
            automation_client=automation_client,
            graph_client=self._graph_client,
            session=self._session,
        )
        executor = ToolExecutor(handlers, publish_event=self._publish_event)
        tools_by_key = {tool.tool_key: tool for tool in tools}
        return await run_tool_based(
            self._registry,
            profile,
            request,
            executor=executor,
            execution=execution,
            tools_by_key=tools_by_key,
            agent_tool_keys=list(profile.allowed_tool_keys),
            granted_categories=granted,
            allow_mutating=allow_mutating,
            max_steps=profile.max_reasoning_steps,
        )


__all__ = ["ExecutionService"]
