"""Request/response schemas for recommendations, reports, feedback,
memory, and analytics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    AiReportType,
    FeedbackRating,
    MemoryScope,
    RecommendationStatus,
    RecommendationType,
)


class RecommendationRequest(BaseModel):
    """Body of ``POST /ai/recommendations``."""

    organization_id: UUID
    project_id: UUID | None = None
    conversation_id: UUID | None = None
    recommendation_type: RecommendationType
    subject: str = Field(min_length=1)


class RecommendationDecisionRequest(BaseModel):
    """Body of ``POST /ai/recommendations/{id}/decide``."""

    accept: bool


class RecommendationResponse(BaseModel):
    """One generated recommendation, with why it was made."""

    id: UUID
    organization_id: UUID
    conversation_id: UUID | None
    recommendation_type: RecommendationType
    title: str
    body: str
    rationale: str | None
    citations: list[dict[str, Any]]
    confidence: float | None
    status: RecommendationStatus
    decided_by: UUID | None


class AiReportRequest(BaseModel):
    """Body of ``POST /ai/reports``."""

    organization_id: UUID
    project_id: UUID | None = None
    conversation_id: UUID | None = None
    report_type: AiReportType
    subject: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class AiReportResponse(BaseModel):
    """One AI-written report."""

    id: UUID
    organization_id: UUID
    conversation_id: UUID | None
    report_type: AiReportType
    title: str
    body: str
    parameters: dict[str, Any]
    citations: list[dict[str, Any]]
    generated_by: UUID | None
    generated_at: datetime


class FeedbackRequest(BaseModel):
    """Body of ``POST /ai/feedback``."""

    organization_id: UUID
    project_id: UUID | None = None
    message_id: UUID
    rating: FeedbackRating
    comment: str | None = None


class FeedbackResponse(BaseModel):
    """One recorded rating."""

    id: UUID
    message_id: UUID
    rating: FeedbackRating
    comment: str | None
    submitted_by: UUID | None


class MemoryCreateRequest(BaseModel):
    """Body of ``POST /ai/memory``."""

    organization_id: UUID
    project_id: UUID | None = None
    scope: MemoryScope
    scope_reference: str = Field(min_length=1, max_length=255)
    key: str = Field(min_length=1, max_length=255)
    value: str = Field(min_length=1)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    expires_at: datetime | None = None


class MemoryResponse(BaseModel):
    """One remembered fact."""

    id: UUID
    scope: MemoryScope
    scope_reference: str
    key: str
    value: str
    importance: float
    expires_at: datetime | None


class AiStatisticsResponse(BaseModel):
    """One organization's cached AI analytics rollup."""

    total_conversations: int
    total_messages: int
    total_tool_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    estimated_cost_usd: float
    average_latency_ms: float
    positive_feedback_rate: float
    recommendation_acceptance_rate: float
    tool_usage: dict[str, Any]
    agent_usage: dict[str, Any]
    model_usage: dict[str, Any]
    computed_at: datetime


__all__ = [
    "AiReportRequest",
    "AiReportResponse",
    "AiStatisticsResponse",
    "FeedbackRequest",
    "FeedbackResponse",
    "MemoryCreateRequest",
    "MemoryResponse",
    "RecommendationDecisionRequest",
    "RecommendationRequest",
    "RecommendationResponse",
]
