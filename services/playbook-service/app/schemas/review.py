"""Request/response schemas for playbook draft reviews."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ReviewStatus


class PlaybookReviewCreateRequest(BaseModel):
    """Body of ``POST /playbooks/{id}/reviews``."""

    version_id: UUID | None = None
    reviewer_id: UUID | None = None


class PlaybookReviewDecisionRequest(BaseModel):
    """Body of ``PATCH /playbooks/reviews/{id}``."""

    status: ReviewStatus
    comments: str | None = Field(default=None, max_length=4096)


class PlaybookReviewResponse(BaseModel):
    """One draft-review step against a playbook (or one of its versions)."""

    id: UUID
    playbook_id: UUID
    version_id: UUID | None
    reviewer_id: UUID | None
    status: ReviewStatus
    comments: str | None
    reviewed_at: datetime | None


__all__ = [
    "PlaybookReviewCreateRequest",
    "PlaybookReviewDecisionRequest",
    "PlaybookReviewResponse",
]
