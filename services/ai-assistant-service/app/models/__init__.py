"""Every AI assistant service entity model.

Importing this package registers all nineteen tables with
:data:`shared_core.database.base.Base.metadata`, which is what
``alembic/env.py`` targets for autogenerate support.
"""

from __future__ import annotations

from app.models.ai_agent import AiAgent
from app.models.ai_audit import AiAuditEntry
from app.models.ai_chunk import AiChunk
from app.models.ai_conversation import AiConversation
from app.models.ai_document import AiDocument
from app.models.ai_embedding import EMBEDDING_DIMENSIONS, AiEmbedding
from app.models.ai_feedback import AiFeedback
from app.models.ai_memory import AiMemory
from app.models.ai_message import AiMessage
from app.models.ai_prompt import AiPrompt
from app.models.ai_prompt_version import AiPromptVersion
from app.models.ai_recommendation import AiRecommendation
from app.models.ai_report import AiReport
from app.models.ai_retrieval_history import AiRetrievalHistory
from app.models.ai_session import AiSession
from app.models.ai_statistics import AiStatistics
from app.models.ai_tool import AiTool
from app.models.ai_tool_call import AiToolCall
from app.models.ai_tool_result import AiToolResult

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "AiAgent",
    "AiAuditEntry",
    "AiChunk",
    "AiConversation",
    "AiDocument",
    "AiEmbedding",
    "AiFeedback",
    "AiMemory",
    "AiMessage",
    "AiPrompt",
    "AiPromptVersion",
    "AiRecommendation",
    "AiReport",
    "AiRetrievalHistory",
    "AiSession",
    "AiStatistics",
    "AiTool",
    "AiToolCall",
    "AiToolResult",
]
