"""Request/response schemas for validation categories."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ValidationType


class ValidationCategoryCreateRequest(BaseModel):
    """Body of a request to create a validation category."""

    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    validation_type: ValidationType


class ValidationCategoryResponse(BaseModel):
    """Groups checks under one validation type."""

    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    validation_type: ValidationType


__all__ = ["ValidationCategoryCreateRequest", "ValidationCategoryResponse"]
