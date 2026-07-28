"""Request/response schemas for templates, categories, and parameters."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    ParameterKind,
    ReportCategory,
    ReportType,
    TemplateStatus,
)


class ParameterDeclaration(BaseModel):
    """One parameter a template declares."""

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    description: str | None = None
    kind: ParameterKind = ParameterKind.STRING
    required: bool = False
    default_value: Any = None
    allowed_values: list[Any] = Field(default_factory=list)
    display_order: int = 0


class ParameterResponse(BaseModel):
    """One declared parameter."""

    id: UUID
    template_id: UUID
    key: str
    label: str
    description: str | None
    kind: ParameterKind
    required: bool
    default_value: Any
    allowed_values: list[Any]
    display_order: int


class TemplateCreateRequest(BaseModel):
    """Body of ``POST /reports/templates``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: ReportCategory
    report_type: ReportType
    category_id: UUID | None = None
    definition: dict[str, Any]
    """The designer document.

    Validated against :class:`~app.reports.designer.schema
    .ReportDefinition` on write, so a malformed template is rejected
    here rather than at render time.
    """

    branding: dict[str, Any] = Field(default_factory=dict)
    parameters: list[ParameterDeclaration] = Field(default_factory=list)


class TemplateVersionRequest(BaseModel):
    """Body of ``POST /reports/templates/{id}/versions``."""

    definition: dict[str, Any]
    branding: dict[str, Any] | None = None
    parameters: list[ParameterDeclaration] = Field(default_factory=list)


class TemplateResponse(BaseModel):
    """One template version."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    category_id: UUID | None
    name: str
    description: str | None
    category: ReportCategory
    report_type: ReportType
    version_number: str
    status: TemplateStatus
    definition: dict[str, Any]
    branding: dict[str, Any]
    is_system: bool
    approved_by: UUID | None
    approved_at: datetime | None


class CategoryCreateRequest(BaseModel):
    """Body of ``POST /reports/categories``."""

    organization_id: UUID
    project_id: UUID | None = None
    category: ReportCategory
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    display_order: int = 0


class CategoryResponse(BaseModel):
    """One report category."""

    id: UUID
    organization_id: UUID
    category: ReportCategory
    slug: str
    name: str
    description: str | None
    display_order: int
    enabled: bool


__all__ = [
    "CategoryCreateRequest",
    "CategoryResponse",
    "ParameterDeclaration",
    "ParameterResponse",
    "TemplateCreateRequest",
    "TemplateResponse",
    "TemplateVersionRequest",
]
