"""Request and response shapes for themes, templates, analytics, and audit."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AuditAction,
    AuditOutcome,
    DashboardType,
    DashboardVisibility,
    ThemeMode,
    TopologyQueryKind,
)


class ThemeCreateRequest(BaseModel):
    """Create a theme."""

    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2_000)
    mode: ThemeMode = ThemeMode.LIGHT
    definition: dict[str, Any] = Field(default_factory=dict)


class ThemeUpdateRequest(BaseModel):
    """Update a theme. Omitted fields are left alone."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2_000)
    mode: ThemeMode | None = None
    definition: dict[str, Any] | None = None


class ThemeSummary(BaseModel):
    """One stored theme."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    mode: ThemeMode
    palette: dict[str, Any]
    branding: dict[str, Any]
    accessibility: dict[str, Any]
    is_system: bool


class ContrastFindingModel(BaseModel):
    """One text/background pair below WCAG AA."""

    pair: str
    ratio: float
    required: float


class ThemeResponse(BaseModel):
    """A theme with any accessibility shortfalls it carries.

    Findings accompany the theme rather than blocking it: a brand colour
    is sometimes fixed by forces outside engineering, and a visible,
    specific shortfall is more useful than a refusal that gets worked
    around by turning the check off.
    """

    theme: ThemeSummary
    contrast_findings: list[ContrastFindingModel] = Field(default_factory=list)


class TemplateCreateRequest(BaseModel):
    """Create a template."""

    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2_000)
    definition: dict[str, Any] = Field(default_factory=dict)


class TemplateCaptureRequest(BaseModel):
    """Turn an existing dashboard into a template."""

    dashboard_id: UUID
    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2_000)


class TemplateApplyRequest(BaseModel):
    """Instantiate a template as a new dashboard."""

    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    project_id: UUID | None = None
    visibility: DashboardVisibility = DashboardVisibility.PRIVATE


class TemplateSummary(BaseModel):
    """One stored template."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    dashboard_type: DashboardType
    is_system: bool
    applied_count: int


class StatisticsResponse(BaseModel):
    """An organization's dashboard analytics rollup."""

    model_config = ConfigDict(from_attributes=True)

    total_dashboards: int
    total_widgets: int
    total_views: int
    unique_viewers: int
    total_shares: int
    average_load_ms: float
    widget_failure_rate: float
    most_viewed: dict[str, Any]
    widget_usage: dict[str, Any]
    dashboard_type_usage: dict[str, Any]
    refresh_usage: dict[str, Any]
    computed_at: datetime


class AuditEntry(BaseModel):
    """One audited dashboard action."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: AuditAction
    outcome: AuditOutcome
    entity_type: str
    entity_id: UUID | None
    actor_id: UUID | None
    reason: str | None
    context: dict[str, Any]
    occurred_at: datetime


class TopologyRequest(BaseModel):
    """One topology traversal."""

    root_id: str = Field(min_length=1, max_length=255)
    kind: TopologyQueryKind = TopologyQueryKind.NEIGHBORS
    depth: int = Field(default=2, ge=1, le=10)


class TopologyResponse(BaseModel):
    """A rendered topology graph."""

    root_id: str
    kind: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    truncated: bool
    node_count: int
    edge_count: int


class PresenceResponse(BaseModel):
    """Who is watching a dashboard right now.

    Scoped to *this replica*: presence is per-process because each
    replica knows only its own connections. Stated in the response so a
    client reading a low number understands why.
    """

    dashboard_id: UUID
    watchers: list[dict[str, Any]]
    replica_scoped: bool = True


__all__ = [
    "AuditEntry",
    "ContrastFindingModel",
    "PresenceResponse",
    "StatisticsResponse",
    "TemplateApplyRequest",
    "TemplateCaptureRequest",
    "TemplateCreateRequest",
    "TemplateSummary",
    "ThemeCreateRequest",
    "ThemeResponse",
    "ThemeSummary",
    "ThemeUpdateRequest",
    "TopologyRequest",
    "TopologyResponse",
]
