"""Dashboard templates ("Template Library").

A template carries the widgets and the layout a new dashboard starts
with. Validating both together on write is the point: a template whose
layout references a widget it does not define would instantiate a
dashboard with a hole in it, and the person applying it would have no
idea why.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator
from shared_core.exceptions.validation import ValidationError

from app.layouts.grid import GridLayout
from app.models.enums import DashboardType, LayoutBreakpoint
from app.widgets.schema import WidgetDefinition


class TemplateLayout(BaseModel):
    """One breakpoint's arrangement within a template."""

    breakpoint: LayoutBreakpoint = LayoutBreakpoint.DESKTOP
    grid: GridLayout = Field(default_factory=GridLayout)


class TemplateDefinition(BaseModel):
    """A complete template document."""

    dashboard_type: DashboardType = DashboardType.CUSTOM
    description: str | None = None
    refresh_seconds: int = Field(default=0, ge=0, le=86_400)
    theme_slug: str | None = Field(default=None, max_length=64)
    default_filters: list[dict[str, Any]] = Field(default_factory=list)
    widgets: list[WidgetDefinition] = Field(default_factory=list)
    layouts: list[TemplateLayout] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_coherence(self) -> TemplateDefinition:
        """Reject a template that would instantiate a broken dashboard."""
        keys = [widget.widget_key for widget in self.widgets]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise ValueError(f"Duplicate widget keys in template: {', '.join(duplicates)}.")

        defined = set(keys)
        seen_breakpoints: set[str] = set()
        for layout in self.layouts:
            breakpoint_name = str(layout.breakpoint)
            if breakpoint_name in seen_breakpoints:
                raise ValueError(f"Template has two {breakpoint_name!r} layouts.")
            seen_breakpoints.add(breakpoint_name)

            placed = layout.grid.widget_keys()
            unknown = sorted(placed - defined)
            if unknown:
                raise ValueError(
                    f"Layout {breakpoint_name!r} places widgets the template does not "
                    f"define: {', '.join(unknown)}."
                )
        return self

    def widget_keys(self) -> set[str]:
        """Every widget key this template defines."""
        return {widget.widget_key for widget in self.widgets}


def parse_template(raw: dict[str, Any]) -> TemplateDefinition:
    """Parse a stored template, raising the platform's own error.

    Raises:
        ValidationError: If the document is malformed or incoherent.
    """
    try:
        return TemplateDefinition.model_validate(raw)
    except Exception as exc:
        raise ValidationError(f"Invalid dashboard template: {exc}") from exc


__all__ = ["TemplateDefinition", "TemplateLayout", "parse_template"]
