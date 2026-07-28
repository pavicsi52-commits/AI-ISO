"""Every AI assistant service repository."""

from __future__ import annotations

from app.repositories.ai_agent import AiAgentRepository
from app.repositories.ai_audit import AiAuditEntryRepository
from app.repositories.ai_chunk import AiChunkRepository
from app.repositories.ai_conversation import AiConversationRepository
from app.repositories.ai_document import AiDocumentRepository
from app.repositories.ai_embedding import AiEmbeddingRepository, SimilarChunk
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

__all__ = [
    "AiAgentRepository",
    "AiAuditEntryRepository",
    "AiChunkRepository",
    "AiConversationRepository",
    "AiDocumentRepository",
    "AiEmbeddingRepository",
    "AiFeedbackRepository",
    "AiMemoryRepository",
    "AiMessageRepository",
    "AiPromptRepository",
    "AiPromptVersionRepository",
    "AiRecommendationRepository",
    "AiReportRepository",
    "AiRetrievalHistoryRepository",
    "AiSessionRepository",
    "AiStatisticsRepository",
    "AiToolCallRepository",
    "AiToolRepository",
    "AiToolResultRepository",
    "SimilarChunk",
]
