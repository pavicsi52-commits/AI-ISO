"""The chat orchestrator -- this service's own central pipeline.

One user turn flows through, in this order:

1. **Screen the input.** An injection attempt is refused outright, with
   the refusal recorded as a normal assistant turn so the conversation
   stays coherent.
2. **Retrieve** relevant passages (RAG), screening each one: a
   retrieved document is untrusted input.
3. **Assemble context** from the system prompt, durable memories, the
   screened passages, and the recent conversation history.
4. **Call the model**, offering only the tools this agent is granted.
5. **Run any requested tool calls**, each authorized, validated,
   executed, and recorded; feed their results back and ask again.
6. **Screen the output** and persist the turn with its citations and
   usage.

Every step's database work is sequential -- ``AsyncSession`` is not
safe for concurrent use even for reads, the real production bug this
platform hit once and has designed around ever since.

The tool loop is bounded by ``max_tool_calls_per_turn``. Without a
bound, a model that keeps requesting tools would loop until something
else broke; with one, it is forced to answer with what it has.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.ai import AIError
from shared_core.logging.logger import get_logger

from app.agents.orchestrator import AgentOrchestrator, aggregate, decompose
from app.clients.base import ChatCompletion, ChatMessage
from app.clients.registry import ModelRegistry
from app.guardrails.engine import (
    screen_model_output,
    screen_retrieved_context,
    screen_user_input,
)
from app.memory.service import MemoryService
from app.models.ai_agent import AiAgent
from app.models.ai_conversation import AiConversation
from app.models.ai_message import AiMessage
from app.models.enums import (
    AgentType,
    ConversationStatus,
    MessageRole,
    ModelProvider,
    RetrievalStrategy,
)
from app.rag.pipeline import RagPipeline, RetrievedPassage
from app.repositories.ai_agent import AiAgentRepository
from app.repositories.ai_conversation import AiConversationRepository
from app.repositories.ai_tool import AiToolRepository
from app.tool_calling.executor import ToolExecutor
from app.tool_calling.registry import to_specification

logger = get_logger("app.services.chat")

INJECTION_REFUSAL = (
    "That request looks like an attempt to override my instructions, so I have not "
    "acted on it. Please rephrase what you actually need."
)


@dataclass(slots=True)
class ChatTurn:
    """Everything one completed turn produced."""

    conversation: AiConversation
    assistant_message: AiMessage
    citations: list[dict[str, Any]] = field(default_factory=list)
    tool_calls_made: int = 0
    guardrail_findings: list[str] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None


class ChatService:
    """Runs a user turn end to end."""

    def __init__(
        self,
        conversations: AiConversationRepository,
        agents: AiAgentRepository,
        tools: AiToolRepository,
        memory: MemoryService,
        rag: RagPipeline,
        registry: ModelRegistry,
        tool_executor: ToolExecutor,
        *,
        default_provider: ModelProvider,
        default_model: str,
        max_tool_calls: int,
        rag_top_k: int,
        max_parallel_agents: int = 5,
    ) -> None:
        self._conversations = conversations
        self._agents = agents
        self._tools = tools
        self._memory = memory
        self._rag = rag
        self._registry = registry
        self._tool_executor = tool_executor
        self._default_provider = default_provider
        self._default_model = default_model
        self._max_tool_calls = max_tool_calls
        self._rag_top_k = rag_top_k
        self._max_parallel_agents = max_parallel_agents

    async def start_conversation(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        user_id: UUID,
        title: str,
        session_id: UUID | None = None,
    ) -> AiConversation:
        """Open a new conversation."""
        return await self._conversations.create(
            AiConversation(
                organization_id=organization_id,
                project_id=project_id,
                session_id=session_id,
                user_id=user_id,
                title=title,
                status=ConversationStatus.ACTIVE,
                started_at=datetime.now(UTC),
            )
        )

    async def _resolve_agent(
        self, organization_id: UUID, agent_type: AgentType | None
    ) -> AiAgent | None:
        enabled = await self._agents.list_enabled_for_org(organization_id)
        if not enabled:
            return None
        if agent_type is not None:
            for agent in enabled:
                if agent.agent_type == agent_type:
                    return agent
        for agent in enabled:
            if agent.agent_type == AgentType.REASONING:
                return agent
        return enabled[0]

    async def _gather_context(
        self, conversation: AiConversation, question: str
    ) -> tuple[list[RetrievedPassage], list[str]]:
        """Retrieve and screen supporting passages."""
        passages = await self._rag.retrieve(
            conversation.organization_id,
            question,
            top_k=self._rag_top_k,
            strategy=RetrievalStrategy.HYBRID,
            conversation_id=conversation.id,
        )
        findings: list[str] = []
        screened: list[RetrievedPassage] = []
        for passage in passages:
            verdict = screen_retrieved_context(passage.content)
            findings.extend(verdict.findings)
            screened.append(
                RetrievedPassage(
                    chunk_id=passage.chunk_id,
                    document_id=passage.document_id,
                    document_title=passage.document_title,
                    document_uri=passage.document_uri,
                    content=verdict.text,
                    score=passage.score,
                )
            )
        return screened, findings

    def _context_block(self, passages: list[RetrievedPassage]) -> str:
        if not passages:
            return ""
        parts = [
            f"[{index + 1}] {passage.document_title}\n{passage.content}"
            for index, passage in enumerate(passages)
        ]
        return "Relevant documentation (cite by number when you use it):\n\n" + "\n\n".join(parts)

    async def send(
        self,
        conversation: AiConversation,
        question: str,
        *,
        caller_permissions: list[str] | None = None,
        allow_mutating_tools: bool = False,
        agent_type: AgentType | None = None,
        requested_by: UUID | None = None,
    ) -> ChatTurn:
        """Run one user turn and return everything it produced.

        Raises:
            AIError: If no agent is configured, or every model provider
                in the fallback chain failed.
        """
        started = time.monotonic()
        await self._memory.record_turn(
            organization_id=conversation.organization_id,
            project_id=conversation.project_id,
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=question,
        )

        input_verdict = screen_user_input(question)
        if input_verdict.is_blocked:
            refusal = await self._memory.record_turn(
                organization_id=conversation.organization_id,
                project_id=conversation.project_id,
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=INJECTION_REFUSAL,
            )
            return ChatTurn(
                conversation=conversation,
                assistant_message=refusal,
                guardrail_findings=list(input_verdict.findings),
            )

        agent = await self._resolve_agent(conversation.organization_id, agent_type)
        if agent is None:
            raise AIError(
                f"No enabled agent is configured for organization "
                f"{conversation.organization_id!r}."
            )

        passages, findings = await self._gather_context(conversation, question)
        memory_block = await self._memory.as_system_context(
            conversation.organization_id,
            conversation_id=conversation.id,
            session_id=conversation.session_id,
            user_id=conversation.user_id,
            project_id=conversation.project_id,
        )

        system_parts = [
            part
            for part in (agent.system_prompt, memory_block, self._context_block(passages))
            if part
        ]
        messages: list[ChatMessage] = []
        if system_parts:
            messages.append(ChatMessage(role=MessageRole.SYSTEM, content="\n\n".join(system_parts)))
        messages.extend(await self._memory.conversation_history(conversation.id))

        available = [
            tool
            for tool in await self._tools.list_enabled_for_org(conversation.organization_id)
            if tool.tool_key in agent.tool_keys
        ]
        specifications = [to_specification(tool) for tool in available]
        tools_by_key = {tool.tool_key: tool for tool in available}

        completion, tool_calls_made = await self._converse(
            conversation,
            messages,
            agent,
            specifications,
            tools_by_key,
            caller_permissions=caller_permissions or [],
            allow_mutating_tools=allow_mutating_tools,
            requested_by=requested_by,
        )

        output_verdict = screen_model_output(completion.content)
        findings.extend(output_verdict.findings)

        assistant_message = await self._memory.record_turn(
            organization_id=conversation.organization_id,
            project_id=conversation.project_id,
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=output_verdict.text,
            model=completion.model,
            provider=completion.provider,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            latency_ms=(time.monotonic() - started) * 1000,
            citations=[passage.as_citation() for passage in passages],
        )

        return ChatTurn(
            conversation=conversation,
            assistant_message=assistant_message,
            citations=[passage.as_citation() for passage in passages],
            tool_calls_made=tool_calls_made,
            guardrail_findings=findings,
            provider=completion.provider,
            model=completion.model,
        )

    async def _converse(
        self,
        conversation: AiConversation,
        messages: list[ChatMessage],
        agent: AiAgent,
        specifications: list[Any],
        tools_by_key: dict[str, Any],
        *,
        caller_permissions: list[str],
        allow_mutating_tools: bool,
        requested_by: UUID | None,
    ) -> tuple[ChatCompletion, int]:
        """Call the model, servicing tool calls until it answers.

        Bounded by ``max_tool_calls``: on reaching the ceiling the model
        is asked once more with no tools offered, which forces a final
        answer instead of another tool request.
        """
        provider = (
            agent.provider
            if isinstance(agent.provider, ModelProvider)
            else ModelProvider(agent.provider)
        )
        working = list(messages)
        calls_made = 0

        while True:
            offer = specifications if calls_made < self._max_tool_calls else []
            completion = await self._registry.chat_with_fallback(
                working,
                provider=provider,
                model=agent.model,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
                tools=offer or None,
            )
            if not completion.tool_calls or not offer:
                return completion, calls_made

            working.append(
                ChatMessage(role=MessageRole.ASSISTANT, content=completion.content or "")
            )
            for requested in completion.tool_calls:
                if calls_made >= self._max_tool_calls:
                    break
                tool = tools_by_key.get(requested.name)
                if tool is None:
                    working.append(
                        ChatMessage(
                            role=MessageRole.TOOL,
                            content=f"Tool {requested.name!r} is not available to this agent.",
                            tool_call_id=requested.call_id,
                            tool_name=requested.name,
                        )
                    )
                    continue

                execution = await self._tool_executor.execute(
                    tool,
                    requested.arguments,
                    organization_id=conversation.organization_id,
                    project_id=conversation.project_id,
                    conversation_id=conversation.id,
                    requested_by=requested_by,
                    agent_tool_keys=list(agent.tool_keys),
                    caller_permissions=caller_permissions,
                    allow_mutating=allow_mutating_tools,
                )
                calls_made += 1
                working.append(
                    ChatMessage(
                        role=MessageRole.TOOL,
                        content=execution.as_model_content(),
                        tool_call_id=requested.call_id,
                        tool_name=requested.name,
                    )
                )

    async def run_multi_agent(
        self, conversation: AiConversation, request: str, *, parallel: bool = False
    ) -> str:
        """Decompose a request across agents and aggregate their answers.

        Exposed separately from :meth:`send` because multi-agent runs
        are a deliberate choice, not the default: they cost one model
        call per task, which is rarely worth it for a single question.
        """
        agents = await self._agents.list_enabled_for_org(conversation.organization_id)
        by_type = {agent.agent_type: agent for agent in agents}
        orchestrator = AgentOrchestrator(
            self._registry, by_type, max_parallel_agents=self._max_parallel_agents
        )
        tasks = decompose(request)
        results = (
            await orchestrator.run_parallel(tasks)
            if parallel
            else await orchestrator.run_sequential(tasks)
        )
        return aggregate(results)

    async def complete_conversation(self, conversation: AiConversation) -> AiConversation:
        """Mark a conversation completed."""
        conversation.status = ConversationStatus.COMPLETED
        conversation.completed_at = datetime.now(UTC)
        return await self._conversations.update(conversation)


__all__ = ["INJECTION_REFUSAL", "ChatService", "ChatTurn"]
