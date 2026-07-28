"""FastAPI dependency injection for the AI assistant service.

One factory per business service, each building its own repositories
from the request-scoped session -- routes depend on services only.

The notable difference from other AI-IOS services: several dependencies
need the **caller's own bearer token**, because every platform read the
assistant performs is made as the asking user. That is what keeps RBAC
enforced by the owning service instead of reimplemented here, and it is
why :data:`CurrentUserToken` exists alongside :data:`CurrentUserId`.
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
from shared_core.notifications.manager import NotificationManager
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.platform import PlatformClient, PlatformEndpoints
from app.clients.registry import ModelRegistry, build_embedding_client, build_local_encoder
from app.memory.service import MemoryService
from app.models.enums import ModelProvider
from app.notifications.ai_notifications import AiNotificationService
from app.prompts.service import PromptService
from app.rag.pipeline import RagPipeline
from app.repositories.ai_agent import AiAgentRepository
from app.repositories.ai_audit import AiAuditEntryRepository
from app.repositories.ai_chunk import AiChunkRepository
from app.repositories.ai_conversation import AiConversationRepository
from app.repositories.ai_document import AiDocumentRepository
from app.repositories.ai_embedding import AiEmbeddingRepository
from app.repositories.ai_feedback import AiFeedbackRepository
from app.repositories.ai_memory import AiMemoryRepository
from app.repositories.ai_message import AiMessageRepository
from app.repositories.ai_prompt import AiPromptRepository
from app.repositories.ai_prompt_version import AiPromptVersionRepository
from app.repositories.ai_recommendation import AiRecommendationRepository
from app.repositories.ai_report import AiReportRepository
from app.repositories.ai_retrieval_history import AiRetrievalHistoryRepository
from app.repositories.ai_session import AiSessionRepository
from app.repositories.ai_statistics import AiStatisticsRepository
from app.repositories.ai_tool import AiToolRepository
from app.repositories.ai_tool_call import AiToolCallRepository
from app.repositories.ai_tool_result import AiToolResultRepository
from app.services.audit import AiAuditService
from app.services.chat import ChatService
from app.services.conversation import ConversationService
from app.services.feedback import FeedbackService
from app.services.recommendation import RecommendationService
from app.services.report import AiReportService
from app.services.statistics import AiStatisticsService
from app.tool_calling.builtin import build_builtin_registry
from app.tool_calling.executor import ToolExecutor

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The process-wide HTTP client shared by every outbound call."""
    return request.app.state.http_client  # type: ignore[no-any-return]


def get_model_registry(request: Request) -> ModelRegistry:
    """The process-wide model provider registry."""
    return request.app.state.model_registry  # type: ignore[no-any-return]


def get_notification_manager(request: Request) -> NotificationManager:
    """The process-wide notification manager."""
    return request.app.state.notification_manager  # type: ignore[no-any-return]


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
    """The raw Bearer token, forwarded to every platform read.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    return credentials.credentials


CurrentUserToken = Annotated[str, Depends(get_caller_token)]


def get_platform_client(
    request: Request,
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    caller_token: CurrentUserToken,
) -> PlatformClient:
    """A platform client bound to *this caller's own* token."""
    settings = request.app.state.service_settings
    return PlatformClient(
        http_client,
        PlatformEndpoints(
            inventory=settings.inventory_service_base_url,
            discovery=settings.discovery_service_base_url,
            configuration=settings.configuration_service_base_url,
            automation=settings.automation_service_base_url,
            workflow=settings.workflow_runtime_service_base_url,
            validation=settings.validation_service_base_url,
            monitoring=settings.monitoring_service_base_url,
            alerting=settings.alerting_service_base_url,
        ),
        caller_token=caller_token,
    )


PlatformDep = Annotated[PlatformClient, Depends(get_platform_client)]


def get_rag_pipeline(
    request: Request,
    session: DbSession,
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> RagPipeline:
    """The current request's fully-wired RAG pipeline."""
    settings = request.app.state.service_settings
    return RagPipeline(
        AiDocumentRepository(session),
        AiChunkRepository(session),
        AiEmbeddingRepository(session),
        AiRetrievalHistoryRepository(session),
        build_local_encoder(settings),
        embedding_client=build_embedding_client(
            http_client, settings, settings.default_embedding_provider
        ),
        embedding_provider=settings.default_embedding_provider,
        embedding_model=settings.default_embedding_model,
        chunk_size=settings.chunk_size_characters,
        chunk_overlap=settings.chunk_overlap_characters,
    )


RagDep = Annotated[RagPipeline, Depends(get_rag_pipeline)]


def get_memory_service(request: Request, session: DbSession) -> MemoryService:
    """The current request's memory service."""
    settings = request.app.state.service_settings
    return MemoryService(
        AiMemoryRepository(session),
        AiMessageRepository(session),
        conversation_turns=settings.conversation_memory_turns,
    )


MemoryDep = Annotated[MemoryService, Depends(get_memory_service)]


def get_tool_executor(session: DbSession, platform: PlatformDep) -> ToolExecutor:
    """The current request's tool executor, with built-in handlers bound."""
    return ToolExecutor(
        AiToolCallRepository(session),
        AiToolResultRepository(session),
        build_builtin_registry(platform),
    )


ToolExecutorDep = Annotated[ToolExecutor, Depends(get_tool_executor)]


def get_chat_service(
    request: Request,
    session: DbSession,
    memory: MemoryDep,
    rag: RagDep,
    registry: Annotated[ModelRegistry, Depends(get_model_registry)],
    tool_executor: ToolExecutorDep,
) -> ChatService:
    """The current request's fully-wired chat orchestrator."""
    settings = request.app.state.service_settings
    return ChatService(
        AiConversationRepository(session),
        AiAgentRepository(session),
        AiToolRepository(session),
        memory,
        rag,
        registry,
        tool_executor,
        default_provider=ModelProvider(settings.default_provider),
        default_model=settings.default_model,
        max_tool_calls=settings.max_tool_calls_per_turn,
        rag_top_k=settings.rag_top_k,
        max_parallel_agents=settings.max_parallel_agents,
    )


ChatSvc = Annotated[ChatService, Depends(get_chat_service)]


def get_conversation_service(session: DbSession) -> ConversationService:
    """The current request's conversation reader."""
    return ConversationService(
        AiConversationRepository(session),
        AiMessageRepository(session),
        AiSessionRepository(session),
    )


ConversationSvc = Annotated[ConversationService, Depends(get_conversation_service)]


def get_prompt_service(session: DbSession) -> PromptService:
    """The current request's prompt service."""
    return PromptService(AiPromptRepository(session), AiPromptVersionRepository(session))


PromptSvc = Annotated[PromptService, Depends(get_prompt_service)]


def get_recommendation_service(session: DbSession) -> RecommendationService:
    """The current request's recommendation service."""
    return RecommendationService(AiRecommendationRepository(session))


RecommendationSvc = Annotated[RecommendationService, Depends(get_recommendation_service)]


def get_report_service(
    request: Request,
    session: DbSession,
    rag: RagDep,
    registry: Annotated[ModelRegistry, Depends(get_model_registry)],
) -> AiReportService:
    """The current request's report generator."""
    settings = request.app.state.service_settings
    return AiReportService(
        AiReportRepository(session),
        rag,
        registry,
        default_provider=ModelProvider(settings.default_provider),
        default_model=settings.default_model,
        rag_top_k=settings.rag_top_k,
    )


ReportSvc = Annotated[AiReportService, Depends(get_report_service)]


def get_feedback_service(session: DbSession) -> FeedbackService:
    """The current request's feedback service."""
    return FeedbackService(AiFeedbackRepository(session))


FeedbackSvc = Annotated[FeedbackService, Depends(get_feedback_service)]


def get_statistics_service(session: DbSession) -> AiStatisticsService:
    """The current request's fully-wired analytics service."""
    return AiStatisticsService(
        AiStatisticsRepository(session),
        AiConversationRepository(session),
        AiMessageRepository(session),
        AiToolCallRepository(session),
        AiFeedbackRepository(session),
        AiRecommendationRepository(session),
    )


StatisticsSvc = Annotated[AiStatisticsService, Depends(get_statistics_service)]


def get_audit_service(session: DbSession) -> AiAuditService:
    """The current request's audit service."""
    return AiAuditService(AiAuditEntryRepository(session))


AuditSvc = Annotated[AiAuditService, Depends(get_audit_service)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> AiNotificationService:
    """The current request's notification service."""
    return AiNotificationService(manager)


NotificationSvc = Annotated[AiNotificationService, Depends(get_notification_service)]


__all__ = [
    "AuditSvc",
    "ChatSvc",
    "ConversationSvc",
    "CurrentUserId",
    "CurrentUserToken",
    "DbSession",
    "FeedbackSvc",
    "MemoryDep",
    "NotificationSvc",
    "PlatformDep",
    "PromptSvc",
    "RagDep",
    "RecommendationSvc",
    "ReportSvc",
    "StatisticsSvc",
    "ToolExecutorDep",
    "get_audit_service",
    "get_caller_token",
    "get_chat_service",
    "get_conversation_service",
    "get_current_user_id",
    "get_db_session",
    "get_feedback_service",
    "get_http_client",
    "get_memory_service",
    "get_model_registry",
    "get_notification_manager",
    "get_notification_service",
    "get_platform_client",
    "get_prompt_service",
    "get_rag_pipeline",
    "get_recommendation_service",
    "get_report_service",
    "get_statistics_service",
    "get_tool_executor",
]
