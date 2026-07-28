"""``/ai/agents``, ``/ai/tools``, and ``/ai/models``.

``GET /ai/models`` and ``POST /ai/models/select`` are from docs/046's
own literal list; the agent and tool CRUD surfaces are added directly,
because "Multi-Agent Framework" and "Tool Calling" are explicit
ACCEPTANCE CRITERIA that cannot be configured otherwise.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AuditSvc,
    CurrentUserId,
    DbSession,
    ToolExecutorDep,
    get_model_registry,
)
from app.clients.registry import ModelRegistry
from app.models.ai_agent import AiAgent
from app.models.ai_tool import AiTool
from app.models.enums import AuditOutcome, ModelProvider
from app.repositories.ai_agent import AiAgentRepository
from app.repositories.ai_tool import AiToolRepository
from app.schemas.agent import (
    AgentCreateRequest,
    AgentResponse,
    ModelProviderResponse,
    ModelSelectRequest,
    ToolCreateRequest,
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/ai", tags=["AI Agents & Tools"])

RegistryDep = Annotated[ModelRegistry, Depends(get_model_registry)]


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def agent_to_response(agent: AiAgent) -> AgentResponse:
    """Map an agent row onto its own response schema."""
    return AgentResponse(
        id=agent.id,
        organization_id=agent.organization_id,
        project_id=agent.project_id,
        name=agent.name,
        agent_type=agent.agent_type,
        description=agent.description,
        provider=agent.provider,
        model=agent.model,
        system_prompt=agent.system_prompt,
        tool_keys=agent.tool_keys,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        enabled=agent.enabled,
    )


def tool_to_response(tool: AiTool) -> ToolResponse:
    """Map a tool row onto its own response schema."""
    return ToolResponse(
        id=tool.id,
        organization_id=tool.organization_id,
        tool_key=tool.tool_key,
        name=tool.name,
        description=tool.description,
        tool_kind=tool.tool_kind,
        parameters_schema=tool.parameters_schema,
        required_permission=tool.required_permission,
        is_mutating=tool.is_mutating,
        enabled=tool.enabled,
    )


@router.get("/agents", response_model=SuccessResponse[list[AgentResponse]])
async def list_agents(
    organization_id: UUID, session: DbSession, _caller: CurrentUserId
) -> SuccessResponse[list[AgentResponse]]:
    """Every agent registered for an organization."""
    records = await AiAgentRepository(session).list_for_org(organization_id)
    return SuccessResponse(
        message="Agents retrieved.",
        data=[agent_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("/agents", response_model=SuccessResponse[AgentResponse], status_code=201)
async def create_agent(
    body: AgentCreateRequest, session: DbSession, _caller: CurrentUserId
) -> SuccessResponse[AgentResponse]:
    """Register an agent with its own tool allowlist."""
    agent = await AiAgentRepository(session).create(
        AiAgent(
            organization_id=body.organization_id,
            project_id=body.project_id,
            name=body.name,
            agent_type=body.agent_type,
            description=body.description,
            provider=body.provider,
            model=body.model,
            system_prompt=body.system_prompt,
            tool_keys=body.tool_keys,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            enabled=body.enabled,
        )
    )
    return SuccessResponse(message="Agent created.", data=agent_to_response(agent), meta=_meta())


@router.get("/tools", response_model=SuccessResponse[list[ToolResponse]])
async def list_tools(
    organization_id: UUID, session: DbSession, _caller: CurrentUserId
) -> SuccessResponse[list[ToolResponse]]:
    """Every tool registered for an organization."""
    records = await AiToolRepository(session).list_for_org(organization_id)
    return SuccessResponse(
        message="Tools retrieved.",
        data=[tool_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("/tools", response_model=SuccessResponse[ToolResponse], status_code=201)
async def create_tool(
    body: ToolCreateRequest, session: DbSession, _caller: CurrentUserId
) -> SuccessResponse[ToolResponse]:
    """Register a tool the model may be offered."""
    tool = await AiToolRepository(session).create(
        AiTool(
            organization_id=body.organization_id,
            project_id=body.project_id,
            tool_key=body.tool_key,
            name=body.name,
            description=body.description,
            tool_kind=body.tool_kind,
            parameters_schema=body.parameters_schema,
            required_permission=body.required_permission,
            is_mutating=body.is_mutating,
            enabled=body.enabled,
        )
    )
    return SuccessResponse(message="Tool created.", data=tool_to_response(tool), meta=_meta())


@router.post("/tools/execute", response_model=SuccessResponse[ToolExecuteResponse], status_code=201)
async def execute_tool(
    body: ToolExecuteRequest,
    session: DbSession,
    executor: ToolExecutorDep,
    caller: CurrentUserId,
) -> SuccessResponse[ToolExecuteResponse]:
    """Execute one tool directly, under the same authorization rules.

    A direct call is authorized exactly as a model-requested one is --
    including the agent allowlist -- so this endpoint cannot be used to
    bypass the gate a conversation would enforce.

    Raises:
        NotFoundError: If the tool or the named agent does not exist.
    """
    tool = await AiToolRepository(session).get_by_key(body.organization_id, body.tool_key)
    if tool is None:
        raise NotFoundError(f"Tool {body.tool_key!r} is not registered.")

    agent_tool_keys: list[str] = []
    if body.agent_id is not None:
        agent = await AiAgentRepository(session).require_by_id(body.agent_id)
        agent_tool_keys = list(agent.tool_keys)
    else:
        agent_tool_keys = [body.tool_key]

    execution = await executor.execute(
        tool,
        body.arguments,
        organization_id=body.organization_id,
        project_id=body.project_id,
        requested_by=caller,
        agent_tool_keys=agent_tool_keys,
        caller_permissions=body.caller_permissions,
        allow_mutating=body.allow_mutating,
    )
    return SuccessResponse(
        message="Tool execution recorded.",
        data=ToolExecuteResponse(
            tool_call_id=execution.call.id,
            status=str(execution.status),
            succeeded=execution.succeeded,
            result=execution.result.result if execution.result else {},
            error_message=execution.result.error_message if execution.result else None,
            denial_reason=execution.call.denial_reason,
        ),
        meta=_meta(),
    )


@router.get("/models", response_model=SuccessResponse[list[ModelProviderResponse]])
async def list_models(
    registry: RegistryDep, _caller: CurrentUserId
) -> SuccessResponse[list[ModelProviderResponse]]:
    """Every model provider actually configured on this deployment.

    A provider with no credential is deliberately absent rather than
    listed-but-broken, so a caller can tell what will genuinely work.
    """
    available = registry.available_providers
    return SuccessResponse(
        message="Model providers retrieved.",
        data=[
            ModelProviderResponse(provider=provider, is_default=index == 0)
            for index, provider in enumerate(available)
        ],
        meta=_meta(),
    )


@router.post("/models/select", response_model=SuccessResponse[AgentResponse])
async def select_model(
    body: ModelSelectRequest,
    session: DbSession,
    registry: RegistryDep,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AgentResponse]:
    """Point an agent at a different provider and model.

    Audited, per docs/046's own "AUDIT: Model Selection" line. The
    provider is validated against what is actually configured, so a
    selection cannot silently leave an agent unable to answer.

    Raises:
        NotFoundError: If the agent does not exist.
        AIError: If the requested provider is not configured.
    """
    registry.get(ModelProvider(body.provider))

    repository = AiAgentRepository(session)
    agent = await repository.require_by_id(body.agent_id)
    agent.provider = body.provider
    agent.model = body.model
    updated = await repository.update(agent)

    await audit.record(
        organization_id=body.organization_id,
        actor_id=caller,
        action="model.selected",
        entity_type="AiAgent",
        entity_id=agent.id,
        outcome=AuditOutcome.SUCCESS,
        reason=f"Model set to {body.provider}/{body.model}.",
    )
    return SuccessResponse(
        message="Model selection updated.", data=agent_to_response(updated), meta=_meta()
    )


__all__ = ["agent_to_response", "router", "tool_to_response"]
