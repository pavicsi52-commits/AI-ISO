"""Agent lifecycle, task, tool, and governance surface (docs/060 "REST
APIs" -- the 15 literal endpoints, all nested under one ``/agents``
prefix).

**Registration order inside this router matters.** Every route with a
static path segment (``/tasks``, ``/tools``, ``/evaluations``,
``/benchmarks``, ``/statistics``, ``/reports``) is declared *before*
``GET/PUT/DELETE /{agent_id}``: FastAPI/Starlette matches routes in
registration order, and ``{agent_id}`` is a catch-all at that same
one-segment shape. Declared first, that catch-all would hijack
``GET /agents/tasks`` as ``agent_id="tasks"`` and fail UUID parsing
before the request ever reached the handler that actually owns the
path -- the same router-ordering bug class already found and fixed in
notification-center-service and plugin-marketplace-service.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AgentsRepo,
    AgentSvc,
    BenchmarksRepo,
    CallerToken,
    CurrentUserId,
    EvaluationsRepo,
    ExecutionSvc,
    ReportSvc,
    StatisticsSvc,
    TasksRepo,
    TaskSvc,
    ToolsRepo,
    ToolSvc,
)
from app.models.enums import AgentType, ReportKind, TaskStatus
from app.schemas.agent import (
    AgentExecuteRequest,
    AgentExecutionResponse,
    AgentRegisterRequest,
    AgentResponse,
    AgentUpdateRequest,
)
from app.schemas.governance import (
    BenchmarkResponse,
    EvaluationResponse,
    ReportResponse,
    StatisticResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.task import TaskCreateRequest, TaskResponse
from app.schemas.tool import ToolRegisterRequest, ToolResponse
from app.services.agent import ProfileFields

router = APIRouter(prefix="/agents", tags=["Agents"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


# ---- static-segment routes first; see this module's own docstring --------


@router.get(
    "/tasks", response_model=SuccessResponse[list[TaskResponse]], summary="List agent tasks"
)
async def list_tasks(
    organization_id: UUID,
    tasks: TasksRepo,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[TaskResponse]]:
    """Tasks queued or completed in this organization, newest first."""
    rows = await tasks.list_for_org(
        organization_id, status=status_filter, limit=limit, offset=offset
    )
    return SuccessResponse(
        message="Tasks listed.", data=[TaskResponse.model_validate(r) for r in rows], meta=_meta()
    )


@router.post(
    "/tasks",
    response_model=SuccessResponse[TaskResponse],
    status_code=201,
    summary="Create an agent task",
)
async def create_task(
    body: TaskCreateRequest, organization_id: UUID, tasks: TaskSvc, caller: CurrentUserId
) -> SuccessResponse[TaskResponse]:
    """Queue a new task."""
    task = await tasks.create_task(
        organization_id=organization_id,
        task_type=body.task_type,
        payload=body.payload,
        agent_id=body.agent_id,
        parent_task_id=body.parent_task_id,
        priority=body.priority,
        scheduled_at=body.scheduled_at,
        max_retries=body.max_retries,
        timeout_seconds=body.timeout_seconds,
        requested_by=str(caller),
    )
    return SuccessResponse(
        message="Task created.", data=TaskResponse.model_validate(task), meta=_meta()
    )


@router.get(
    "/tools", response_model=SuccessResponse[list[ToolResponse]], summary="List agent tools"
)
async def list_tools(
    organization_id: UUID,
    tools: ToolsRepo,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ToolResponse]]:
    """Tools registered in this organization, newest first."""
    rows = await tools.list_for_org(organization_id, limit=limit, offset=offset)
    return SuccessResponse(
        message="Tools listed.", data=[ToolResponse.model_validate(r) for r in rows], meta=_meta()
    )


@router.post(
    "/tools",
    response_model=SuccessResponse[ToolResponse],
    status_code=201,
    summary="Register a tool",
)
async def register_tool(
    body: ToolRegisterRequest, organization_id: UUID, tools: ToolSvc
) -> SuccessResponse[ToolResponse]:
    """Register a new tool in this organization's own tool catalogue."""
    tool = await tools.register_tool(
        organization_id=organization_id,
        tool_key=body.tool_key,
        name=body.name,
        tool_kind=body.tool_kind,
        description=body.description,
        category=body.category,
        parameters_schema=body.parameters_schema,
        required_permission=body.required_permission,
        is_mutating=body.is_mutating,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Tool registered.", data=ToolResponse.model_validate(tool), meta=_meta()
    )


@router.get(
    "/evaluations",
    response_model=SuccessResponse[list[EvaluationResponse]],
    summary="List agent evaluations",
)
async def list_evaluations(
    organization_id: UUID,
    evaluations: EvaluationsRepo,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[EvaluationResponse]]:
    """Scored evaluations in this organization, newest first."""
    rows = await evaluations.list_for_org(organization_id, limit=limit, offset=offset)
    return SuccessResponse(
        message="Evaluations listed.",
        data=[EvaluationResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/benchmarks",
    response_model=SuccessResponse[list[BenchmarkResponse]],
    summary="List agent benchmark runs",
)
async def list_benchmarks(
    organization_id: UUID,
    benchmarks: BenchmarksRepo,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[BenchmarkResponse]]:
    """Benchmark suite runs in this organization, newest first."""
    rows = await benchmarks.list_for_org(organization_id, limit=limit, offset=offset)
    return SuccessResponse(
        message="Benchmarks listed.",
        data=[BenchmarkResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/statistics",
    response_model=SuccessResponse[StatisticResponse | None],
    summary="Latest rolled-up agent activity",
)
async def get_statistics(
    organization_id: UUID, statistics: StatisticsSvc
) -> SuccessResponse[StatisticResponse | None]:
    """This organization's own most recently computed statistics window."""
    latest = await statistics.trend(organization_id, since_days=3650)
    data = StatisticResponse.model_validate(latest[-1]) if latest else None
    return SuccessResponse(message="Statistics retrieved.", data=data, meta=_meta())


@router.get(
    "/reports",
    response_model=SuccessResponse[list[ReportResponse]],
    summary="List generated agent reports",
)
async def list_reports(
    organization_id: UUID,
    reports: ReportSvc,
    kind: ReportKind | None = None,
) -> SuccessResponse[list[ReportResponse]]:
    """Generated reports in this organization, newest first."""
    rows = await reports.list_for_org(organization_id, kind=kind)
    return SuccessResponse(
        message="Reports listed.",
        data=[ReportResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


# ---- collection-root routes (no path-arity collision) ---------------------


@router.get("", response_model=SuccessResponse[list[AgentResponse]], summary="List agents")
async def list_agents(
    organization_id: UUID,
    agents: AgentsRepo,
    agent_type: AgentType | None = None,
) -> SuccessResponse[list[AgentResponse]]:
    """Agents registered in this organization."""
    rows = (
        await agents.list_by_type(organization_id, agent_type)
        if agent_type is not None
        else await agents.list_for_org(organization_id)
    )
    return SuccessResponse(
        message="Agents listed.", data=[AgentResponse.model_validate(r) for r in rows], meta=_meta()
    )


@router.post(
    "", response_model=SuccessResponse[AgentResponse], status_code=201, summary="Register an agent"
)
async def register_agent(
    body: AgentRegisterRequest, organization_id: UUID, agents: AgentSvc, caller: CurrentUserId
) -> SuccessResponse[AgentResponse]:
    """Register a new agent, its own initial profile, and first version."""
    agent = await agents.register(
        organization_id=organization_id,
        slug=body.slug,
        name=body.name,
        agent_type=body.agent_type,
        description=body.description,
        owner_id=body.owner_id,
        tags=body.tags,
        profile=ProfileFields(
            system_prompt=body.profile.system_prompt,
            model_provider=body.profile.model_provider,
            model_name=body.profile.model_name,
            temperature=body.profile.temperature,
            max_tokens=body.profile.max_tokens,
            reasoning_mode=body.profile.reasoning_mode,
            routing_strategy=body.profile.routing_strategy,
            fallback_providers=[str(p) for p in body.profile.fallback_providers],
            allowed_tool_keys=body.profile.allowed_tool_keys,
            max_reasoning_steps=body.profile.max_reasoning_steps,
            extra_config=body.profile.extra_config,
        ),
        registered_by=str(caller),
    )
    return SuccessResponse(
        message="Agent registered.", data=AgentResponse.model_validate(agent), meta=_meta()
    )


# ---- single-agent routes: the {agent_id} catch-all and its own sub-paths --


@router.get("/{agent_id}", response_model=SuccessResponse[AgentResponse], summary="Get one agent")
async def get_agent(
    agent_id: UUID, organization_id: UUID, agents: AgentsRepo
) -> SuccessResponse[AgentResponse]:
    """One registered agent."""
    agent = await agents.require_in_org(organization_id, agent_id)
    return SuccessResponse(
        message="Agent retrieved.", data=AgentResponse.model_validate(agent), meta=_meta()
    )


@router.put("/{agent_id}", response_model=SuccessResponse[AgentResponse], summary="Update an agent")
async def update_agent(
    agent_id: UUID,
    organization_id: UUID,
    body: AgentUpdateRequest,
    agents_repo: AgentsRepo,
    agents: AgentSvc,
) -> SuccessResponse[AgentResponse]:
    """Update one agent's own identity fields."""
    agent = await agents_repo.require_in_org(organization_id, agent_id)
    updated = await agents.update(
        agent, name=body.name, description=body.description, tags=body.tags, owner_id=body.owner_id
    )
    return SuccessResponse(
        message="Agent updated.", data=AgentResponse.model_validate(updated), meta=_meta()
    )


@router.delete(
    "/{agent_id}", response_model=SuccessResponse[AgentResponse], summary="Retire an agent"
)
async def retire_agent(
    agent_id: UUID,
    organization_id: UUID,
    agents_repo: AgentsRepo,
    agents: AgentSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AgentResponse]:
    """Retire one agent permanently."""
    agent = await agents_repo.require_in_org(organization_id, agent_id)
    retired = await agents.retire(agent, retired_by=str(caller))
    return SuccessResponse(
        message="Agent retired.", data=AgentResponse.model_validate(retired), meta=_meta()
    )


@router.post(
    "/{agent_id}/execute",
    response_model=SuccessResponse[AgentExecutionResponse],
    status_code=201,
    summary="Execute an agent",
)
async def execute_agent(
    agent_id: UUID,
    organization_id: UUID,
    body: AgentExecuteRequest,
    agents_repo: AgentsRepo,
    executions: ExecutionSvc,
    caller_token: CallerToken,
) -> SuccessResponse[AgentExecutionResponse]:
    """Run one agent against a request."""
    agent = await agents_repo.require_in_org(organization_id, agent_id)
    execution = await executions.execute_agent(
        agent,
        request=body.request,
        session_id=body.session_id,
        task_id=body.task_id,
        caller_token=caller_token,
        allow_mutating=body.allow_mutating,
    )
    return SuccessResponse(
        message="Agent executed.",
        data=AgentExecutionResponse.model_validate(execution),
        meta=_meta(),
    )


@router.post(
    "/{agent_id}/pause", response_model=SuccessResponse[AgentResponse], summary="Pause an agent"
)
async def pause_agent(
    agent_id: UUID, organization_id: UUID, agents_repo: AgentsRepo, agents: AgentSvc
) -> SuccessResponse[AgentResponse]:
    """Pause an active agent so it stops being dispatched."""
    agent = await agents_repo.require_in_org(organization_id, agent_id)
    paused = await agents.pause(agent)
    return SuccessResponse(
        message="Agent paused.", data=AgentResponse.model_validate(paused), meta=_meta()
    )


@router.post(
    "/{agent_id}/resume", response_model=SuccessResponse[AgentResponse], summary="Resume an agent"
)
async def resume_agent(
    agent_id: UUID, organization_id: UUID, agents_repo: AgentsRepo, agents: AgentSvc
) -> SuccessResponse[AgentResponse]:
    """Resume a paused agent."""
    agent = await agents_repo.require_in_org(organization_id, agent_id)
    resumed = await agents.resume(agent)
    return SuccessResponse(
        message="Agent resumed.", data=AgentResponse.model_validate(resumed), meta=_meta()
    )


__all__ = ["router"]
