"""FastAPI dependency injection for the AI agent platform service.

One factory per business service, each building its own repositories
from the request-scoped session -- routes depend on services only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.registry import ModelRegistry
from app.graph.client import GraphClient
from app.memory.service import MemoryService
from app.repositories.agent import AgentRepository, AgentVersionRepository
from app.repositories.benchmark import AgentBenchmarkRepository
from app.repositories.evaluation import AgentEvaluationRepository
from app.repositories.execution import AgentExecutionRepository
from app.repositories.governance import (
    AgentAuditRepository,
    AgentReportRepository,
    AgentStatisticRepository,
)
from app.repositories.memory import AgentMemoryRepository
from app.repositories.permission import AgentPermissionGrantRepository
from app.repositories.profile import AgentProfileRepository
from app.repositories.task import AgentTaskRepository
from app.repositories.tool import AgentToolRepository
from app.sandbox.policy import AgentSandboxPolicy
from app.services.agent import AgentService
from app.services.execution import ExecutionService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.task import TaskService
from app.services.tool import ToolService
from app.types import EventPublisher

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_event_publisher(request: Request) -> EventPublisher:
    """The process-wide domain-event publisher."""
    return request.app.state.publish_event  # type: ignore[no-any-return]


EventPublisherDep = Annotated[EventPublisher, Depends(get_event_publisher)]


async def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UUID:
    """Resolve the calling user's id from their Bearer token.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    public_key = request.app.state.jwt_public_key
    claims = decode_token(credentials.credentials, public_key=public_key)
    return UUID(str(claims["sub"]))


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


async def get_caller_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """The raw Bearer token, forwarded as-is to sibling services an
    agent's own tool calls reach live (Automation, Policy Engine) --
    an agent's own automation call must act with the authority of
    whoever triggered it, never a fixed service credential.
    """
    return credentials.credentials if credentials is not None else ""


CallerToken = Annotated[str, Depends(get_caller_token)]


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The process-wide outbound HTTP client."""
    return request.app.state.http_client  # type: ignore[no-any-return]


HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]


def get_model_registry(request: Request) -> ModelRegistry:
    """The process-wide model provider registry."""
    return request.app.state.model_registry  # type: ignore[no-any-return]


ModelRegistryDep = Annotated[ModelRegistry, Depends(get_model_registry)]


def get_graph_client(request: Request) -> GraphClient | None:
    """The process-wide Neo4j client, or ``None`` if unconfigured."""
    return request.app.state.graph_client  # type: ignore[no-any-return]


GraphClientDep = Annotated[GraphClient | None, Depends(get_graph_client)]


def get_sandbox_policy(request: Request) -> AgentSandboxPolicy:
    """The process-wide default agent sandbox policy."""
    return request.app.state.sandbox_policy  # type: ignore[no-any-return]


SandboxPolicyDep = Annotated[AgentSandboxPolicy, Depends(get_sandbox_policy)]


def get_agent_service(session: DbSession, publish_event: EventPublisherDep) -> AgentService:
    """The current request's agent lifecycle service."""
    return AgentService(
        AgentRepository(session),
        AgentProfileRepository(session),
        AgentVersionRepository(session),
        AgentAuditRepository(session),
        publish_event=publish_event,
    )


AgentSvc = Annotated[AgentService, Depends(get_agent_service)]


def get_task_service(session: DbSession, publish_event: EventPublisherDep) -> TaskService:
    """The current request's task management service."""
    return TaskService(AgentTaskRepository(session), publish_event=publish_event)


TaskSvc = Annotated[TaskService, Depends(get_task_service)]


def get_tool_service(session: DbSession) -> ToolService:
    """The current request's tool registry service."""
    return ToolService(AgentToolRepository(session))


ToolSvc = Annotated[ToolService, Depends(get_tool_service)]


def get_execution_service(
    session: DbSession,
    publish_event: EventPublisherDep,
    http_client: HttpClientDep,
    sandbox_policy: SandboxPolicyDep,
    graph_client: GraphClientDep,
    registry: ModelRegistryDep,
    request: Request,
) -> ExecutionService:
    """The current request's agent execution service."""
    settings = request.app.state.service_settings
    return ExecutionService(
        AgentRepository(session),
        AgentProfileRepository(session),
        AgentToolRepository(session),
        AgentPermissionGrantRepository(session),
        AgentExecutionRepository(session),
        MemoryService(AgentMemoryRepository(session)),
        registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        graph_client=graph_client,
        automation_service_base_url=settings.automation_service_base_url,
        session=session,
        publish_event=publish_event,
    )


ExecutionSvc = Annotated[ExecutionService, Depends(get_execution_service)]


def get_agents_repo(session: DbSession) -> AgentRepository:
    """The current request's agent repository (read-only lookups from the API)."""
    return AgentRepository(session)


AgentsRepo = Annotated[AgentRepository, Depends(get_agents_repo)]


def get_tasks_repo(session: DbSession) -> AgentTaskRepository:
    """The current request's task repository (read-only listing from the API)."""
    return AgentTaskRepository(session)


TasksRepo = Annotated[AgentTaskRepository, Depends(get_tasks_repo)]


def get_tools_repo(session: DbSession) -> AgentToolRepository:
    """The current request's tool repository (read-only listing from the API)."""
    return AgentToolRepository(session)


ToolsRepo = Annotated[AgentToolRepository, Depends(get_tools_repo)]


def get_evaluations_repo(session: DbSession) -> AgentEvaluationRepository:
    """The current request's evaluation repository (read-only from the API)."""
    return AgentEvaluationRepository(session)


EvaluationsRepo = Annotated[AgentEvaluationRepository, Depends(get_evaluations_repo)]


def get_benchmarks_repo(session: DbSession) -> AgentBenchmarkRepository:
    """The current request's benchmark repository (read-only from the API)."""
    return AgentBenchmarkRepository(session)


BenchmarksRepo = Annotated[AgentBenchmarkRepository, Depends(get_benchmarks_repo)]


def get_statistics_service(session: DbSession) -> StatisticsService:
    """The current request's statistics service."""
    return StatisticsService(
        AgentStatisticRepository(session),
        AgentRepository(session),
        AgentTaskRepository(session),
        AgentExecutionRepository(session),
        AgentMemoryRepository(session),
    )


StatisticsSvc = Annotated[StatisticsService, Depends(get_statistics_service)]


def get_report_service(session: DbSession, request: Request) -> ReportService:
    """The current request's report service."""
    settings = request.app.state.service_settings
    return ReportService(
        AgentReportRepository(session),
        AgentRepository(session),
        AgentExecutionRepository(session),
        AgentAuditRepository(session),
        max_rows=settings.max_report_rows,
    )


ReportSvc = Annotated[ReportService, Depends(get_report_service)]


def get_audit_service(session: DbSession) -> AuditService:
    """The current request's audit service."""
    return AuditService(AgentAuditRepository(session))


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]


__all__ = [
    "AgentSvc",
    "AgentsRepo",
    "AuditSvc",
    "BenchmarksRepo",
    "CallerToken",
    "CurrentUserId",
    "DbSession",
    "EvaluationsRepo",
    "EventPublisherDep",
    "ExecutionSvc",
    "GraphClientDep",
    "HttpClientDep",
    "ModelRegistryDep",
    "ReportSvc",
    "SandboxPolicyDep",
    "StatisticsSvc",
    "TaskSvc",
    "TasksRepo",
    "ToolSvc",
    "ToolsRepo",
    "get_agent_service",
    "get_agents_repo",
    "get_audit_service",
    "get_benchmarks_repo",
    "get_caller_token",
    "get_current_user_id",
    "get_db_session",
    "get_evaluations_repo",
    "get_event_publisher",
    "get_execution_service",
    "get_graph_client",
    "get_http_client",
    "get_model_registry",
    "get_report_service",
    "get_sandbox_policy",
    "get_statistics_service",
    "get_task_service",
    "get_tasks_repo",
    "get_tool_service",
    "get_tools_repo",
]
