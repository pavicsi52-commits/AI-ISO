"""The rendered report document.

The renderer resolves a :class:`~app.reports.designer.schema
.ReportDefinition` into one of these -- data fetched, filters applied,
metrics computed, AI prose written -- and every exporter then
serialises *this* rather than re-interpreting the designer document.

That split is what keeps seven export formats honest: a number is
aggregated once, in one place, so the PDF and the CSV cannot disagree
about what the report says.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.enums import ChartKind, SectionKind
from app.reports.designer.schema import Branding


@dataclass(frozen=True, slots=True)
class RenderedColumn:
    """One resolved table column."""

    key: str
    label: str
    width: float | None = None


@dataclass(slots=True)
class RenderedSection:
    """One resolved section, ready to serialise.

    Every field an exporter might need is present and already
    computed; an exporter never reaches back to a data source.

    ``error`` carries a section that could not be resolved. A failed
    section does not fail the report -- an infrastructure report whose
    monitoring source is down is still worth delivering with that one
    section marked unavailable, and hiding the gap would be worse than
    showing it.
    """

    key: str
    kind: SectionKind
    title: str | None = None
    text: str | None = None
    columns: list[RenderedColumn] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    metric_value: float | None = None
    metric_label: str | None = None
    chart_kind: ChartKind | None = None
    chart_points: list[tuple[str, float]] = field(default_factory=list)
    error: str | None = None

    @property
    def failed(self) -> bool:
        """Whether this section could not be resolved."""
        return self.error is not None

    def cell_values(self) -> list[list[str]]:
        """Rows rendered as strings, in column order.

        Shared by every tabular exporter so CSV, XLSX, HTML, Markdown,
        and PDF cannot format the same cell differently.
        """
        return [[_stringify(row.get(column.key)) for column in self.columns] for row in self.rows]


def _stringify(value: Any) -> str:
    """Render one cell value as text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return ", ".join(_stringify(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{key}={_stringify(item)}" for key, item in sorted(value.items()))
    return str(value)


@dataclass(slots=True)
class RenderedReport:
    """A fully resolved report."""

    title: str
    subtitle: str | None
    branding: Branding
    sections: list[RenderedSection]
    generated_at: datetime
    parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def total_rows(self) -> int:
        """Rows across every table section."""
        return sum(len(section.rows) for section in self.sections)

    @property
    def failed_sections(self) -> list[RenderedSection]:
        """Sections that could not be resolved."""
        return [section for section in self.sections if section.failed]

    def as_dict(self) -> dict[str, Any]:
        """The report as plain JSON-serialisable data.

        Backs the JSON exporter and is also what the XML exporter walks,
        so those two can never drift apart.
        """
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "generated_at": self.generated_at.isoformat(),
            "company": self.branding.company_name,
            "parameters": {key: _stringify(value) for key, value in self.parameters.items()},
            "sections": [
                {
                    "key": section.key,
                    "kind": str(section.kind),
                    "title": section.title,
                    "text": section.text,
                    "error": section.error,
                    "columns": [
                        {"key": column.key, "label": column.label} for column in section.columns
                    ],
                    "rows": section.rows,
                    "metric_value": section.metric_value,
                    "metric_label": section.metric_label,
                    "chart_kind": str(section.chart_kind) if section.chart_kind else None,
                    "chart_points": [
                        {"label": label, "value": value} for label, value in section.chart_points
                    ],
                }
                for section in self.sections
            ],
        }


__all__ = ["RenderedColumn", "RenderedReport", "RenderedSection"]
