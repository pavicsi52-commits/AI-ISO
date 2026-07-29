"""Request and response shapes for dashboards, widgets, and layouts.

These are the HTTP boundary. They deliberately do **not** re-implement
the domain validation that lives in :mod:`app.widgets.schema` and
:mod:`app.layouts.grid` -- a widget definition arrives as a dict and is
parsed by the module that owns its meaning, so there is exactly one
place where "can this widget render?" is decided.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    DashboardType,
    DashboardVisibility,
    LayoutBreakpoint,
    RefreshMode,
    WidgetStatus,
    WidgetType,
)


class DashboardCreateRequest(BaseModel):
    """Create one dashboard."""

    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2_000)
    dashboard_type: DashboardType = DashboardType.CUSTOM
    visibility: DashboardVisibility = DashboardVisibility.PRIVATE
    project_id: UUID | None = None
    theme_id: UUID | None = None
    default_filters: list[dict[str, Any]] = Field(default_factory=list)
    refresh_seconds: int = Field(default=0, ge=0, le=86_400)


class DashboardUpdateRequest(BaseModel):
    """Update one dashboard. Omitted fields are left alone."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2_000)
    visibility: DashboardVisibility | None = None
    theme_id: UUID | None = None
    default_filters: list[dict[str, Any]] | None = None
    refresh_seconds: int | None = Field(default=None, ge=0, le=86_400)
    enabled: bool | None = None


class DashboardSummary(BaseModel):
    """One dashboard, without its widgets."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    dashboard_type: DashboardType
    visibility: DashboardVisibility
    owner_id: UUID | None
    theme_id: UUID | None
    refresh_seconds: int
    layout_revision: int
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WidgetCreateRequest(BaseModel):
    """Add one widget to a dashboard.

    ``definition`` is the authored widget document, validated by
    :func:`app.widgets.schema.parse_widget` rather than here.
    """

    dashboard_id: UUID
    definition: dict[str, Any]
    refresh_mode: RefreshMode = RefreshMode.POLLING
    refresh_seconds: int = Field(default=60, ge=0, le=86_400)
    cache_seconds: int = Field(default=30, ge=0, le=86_400)


class WidgetSummary(BaseModel):
    """One stored widget."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dashboard_id: UUID
    widget_key: str
    title: str
    widget_type: WidgetType
    refresh_mode: RefreshMode
    refresh_seconds: int
    cache_seconds: int
    display_order: int
    enabled: bool


class WidgetSettingRequest(BaseModel):
    """One user's own overrides for one widget."""

    collapsed: bool | None = None
    hidden: bool | None = None
    refresh_seconds_override: int | None = None
    options_override: dict[str, Any] | None = None


class PlacementModel(BaseModel):
    """One widget's position and size, as sent over HTTP."""

    widget_key: str = Field(min_length=1, max_length=64)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=1)
    h: int = Field(ge=1)


class LayoutSaveRequest(BaseModel):
    """Save a new layout revision."""

    dashboard_id: UUID
    breakpoint_: LayoutBreakpoint = Field(default=LayoutBreakpoint.DESKTOP, alias="breakpoint")
    placements: list[PlacementModel] = Field(default_factory=list)
    columns: int = Field(default=12, ge=1, le=48)
    row_height: int = Field(default=60, ge=10, le=500)
    name: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(populate_by_name=True)


class LayoutRestoreRequest(BaseModel):
    """Restore an earlier layout revision."""

    breakpoint_: LayoutBreakpoint = Field(default=LayoutBreakpoint.DESKTOP, alias="breakpoint")
    revision: int = Field(ge=1)

    model_config = ConfigDict(populate_by_name=True)


class LayoutSummary(BaseModel):
    """One saved layout revision."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dashboard_id: UUID
    breakpoint: LayoutBreakpoint
    revision: int
    name: str | None
    columns: int
    row_height: int
    is_current: bool
    placements: list[dict[str, Any]]


class GridResponse(BaseModel):
    """A resolved arrangement, ready to render."""

    columns: int
    row_height: int
    placements: list[PlacementModel]


class ResolvedWidgetResponse(BaseModel):
    """One widget resolved for display."""

    widget_key: str
    widget_type: WidgetType
    title: str
    status: WidgetStatus
    payload: dict[str, Any]
    error: str | None
    row_count: int
    duration_ms: float | None


class DashboardLoadResponse(BaseModel):
    """A complete dashboard load."""

    dashboard: DashboardSummary
    layout: GridResponse
    widgets: list[ResolvedWidgetResponse]
    failed_widgets: list[str]
    load_ms: float | None


class HistoryEntry(BaseModel):
    """One activity entry on a dashboard."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event: str
    summary: str
    details: dict[str, Any]
    layout_revision: int | None
    actor_id: UUID | None
    occurred_at: datetime


class SavedFilterRequest(BaseModel):
    """Save a named filter set."""

    name: str = Field(min_length=1, max_length=255)
    clauses: list[dict[str, Any]] = Field(default_factory=list)
    shared: bool = False
    """Save as a dashboard-wide preset rather than a personal filter."""

    is_default: bool = False


class SavedFilterSummary(BaseModel):
    """One saved filter set."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dashboard_id: UUID
    user_id: UUID | None
    name: str
    clauses: list[dict[str, Any]]
    is_default: bool


class FavoriteReorderRequest(BaseModel):
    """Set the order of a user's favourites."""

    dashboard_ids: list[UUID] = Field(default_factory=list)


__all__ = [
    "DashboardCreateRequest",
    "DashboardLoadResponse",
    "DashboardSummary",
    "DashboardUpdateRequest",
    "FavoriteReorderRequest",
    "GridResponse",
    "HistoryEntry",
    "LayoutRestoreRequest",
    "LayoutSaveRequest",
    "LayoutSummary",
    "PlacementModel",
    "ResolvedWidgetResponse",
    "SavedFilterRequest",
    "SavedFilterSummary",
    "WidgetCreateRequest",
    "WidgetSettingRequest",
    "WidgetSummary",
]
