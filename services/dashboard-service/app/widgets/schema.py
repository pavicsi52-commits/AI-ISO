"""Widget definitions ("WIDGET TYPES", "Widget Library").

A widget's ``query`` and ``options`` are JSON columns, which the
database cannot police. This module is what makes them honest: every
write path validates against these models, so a widget that cannot
possibly render is rejected at authoring time rather than appearing as
a broken tile on someone's dashboard at 09:00.

**Why JSON rather than tables.** Eighteen widget types need genuinely
different options -- a gauge has thresholds, a table has columns, a
topology graph has a traversal depth. Normalising that would mean
either eighteen sparse column sets or a migration every time a widget
gains an option, and would turn "give me this widget as authored" into
a multi-table join.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import DataSource, TopologyQueryKind, WidgetType

CHART_TYPES = frozenset(
    {
        WidgetType.LINE_CHART,
        WidgetType.BAR_CHART,
        WidgetType.AREA_CHART,
        WidgetType.PIE_CHART,
        WidgetType.DONUT_CHART,
    }
)
"""Widget types that plot a label/value series."""

TABULAR_TYPES = frozenset({WidgetType.TABLE, WidgetType.STATUS_MATRIX, WidgetType.TREE_VIEW})
"""Widget types that render rows and columns."""

FEED_TYPES = frozenset({WidgetType.ALERT_FEED, WidgetType.EVENT_FEED, WidgetType.TIMELINE})
"""Widget types that render a reverse-chronological list."""

STATIC_TYPES = frozenset({WidgetType.MARKDOWN})
"""Widget types that need no data source at all."""

_AGGREGATES = ("count", "sum", "avg", "min", "max", "latest")


class WidgetQuery(BaseModel):
    """Where a widget gets its rows.

    ``path`` is relative to the source service's own base URL, so a
    widget never hardcodes a host and stays portable between
    environments. ``CUSTOM_API`` is the single exception and requires
    an absolute URL, which :mod:`app.clients.platform` validates.
    """

    source: DataSource = DataSource.STATIC
    path: str = Field(default="", max_length=1024)
    params: dict[str, Any] = Field(default_factory=dict)
    result_path: str | None = Field(default=None, max_length=255)
    """Dotted path into the response envelope, e.g. ``data.items``.

    Defaults to the platform's own ``data`` key when omitted, which is
    what every AI-IOS service returns.
    """

    @model_validator(mode="after")
    def _require_a_path_for_network_sources(self) -> WidgetQuery:
        if self.source is not DataSource.STATIC and not self.path:
            raise ValueError(f"A {self.source} query requires a path.")
        return self


class ColumnSpec(BaseModel):
    """One column of a tabular widget."""

    key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=255)
    width: int | None = Field(default=None, gt=0)
    align: Literal["left", "center", "right"] = "left"


class Threshold(BaseModel):
    """One coloured band on a gauge or metric card.

    ``at`` is the lower bound of the band. Bands are sorted on
    validation, so a caller cannot produce an ambiguous ordering by
    listing them out of sequence.
    """

    at: float
    color: str = Field(min_length=1, max_length=32)
    label: str | None = Field(default=None, max_length=64)


class SeriesSpec(BaseModel):
    """How a chart widget turns rows into a plotted series."""

    label_key: str = Field(min_length=1, max_length=128)
    value_key: str = Field(min_length=1, max_length=128)
    aggregate: Literal["count", "sum", "avg", "min", "max", "latest"] = "sum"
    max_points: int = Field(default=50, ge=1, le=500)
    """Categories beyond this are aggregated into "Other".

    Truncating silently would misreport the total, so the remainder is
    summed rather than dropped.
    """


class TopologySpec(BaseModel):
    """How a topology widget traverses the graph."""

    kind: TopologyQueryKind = TopologyQueryKind.NEIGHBORS
    root_key: str = Field(default="asset_id", max_length=64)
    """Which parameter carries the starting node."""

    depth: int = Field(default=2, ge=1, le=10)
    include_labels: list[str] = Field(default_factory=list)


class MetricSpec(BaseModel):
    """How a metric card or gauge reduces rows to one number."""

    value_key: str | None = Field(default=None, max_length=128)
    aggregate: Literal["count", "sum", "avg", "min", "max", "latest"] = "count"
    unit: str | None = Field(default=None, max_length=32)
    precision: int = Field(default=0, ge=0, le=6)

    @model_validator(mode="after")
    def _non_count_aggregates_need_a_key(self) -> MetricSpec:
        if self.aggregate != "count" and not self.value_key:
            raise ValueError(f"Aggregate {self.aggregate!r} requires a value_key.")
        return self


class WidgetOptions(BaseModel):
    """Everything type-specific about how a widget renders.

    One model with optional sub-specs rather than eighteen classes: the
    validator below enforces that the sub-spec a type *needs* is
    present, which is the part that actually prevents a broken widget,
    while keeping the stored JSON one predictable shape.
    """

    columns: list[ColumnSpec] = Field(default_factory=list)
    series: SeriesSpec | None = None
    metric: MetricSpec | None = None
    thresholds: list[Threshold] = Field(default_factory=list)
    topology: TopologySpec | None = None
    content: str | None = None
    """Markdown body, for a ``MARKDOWN`` widget."""

    ai_prompt: str | None = None
    """Instruction for an ``AI_INSIGHT`` widget, sent to Prompt 046."""

    limit: int = Field(default=25, ge=1, le=1000)
    """Row ceiling for feeds and tables."""

    show_legend: bool = True
    stacked: bool = False

    @model_validator(mode="after")
    def _sort_thresholds(self) -> WidgetOptions:
        """Keep bands in ascending order so lookup is unambiguous."""
        if self.thresholds:
            self.thresholds = sorted(self.thresholds, key=lambda band: band.at)
        return self


class WidgetDefinition(BaseModel):
    """A complete widget, as authored."""

    widget_key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    widget_type: WidgetType
    query: WidgetQuery = Field(default_factory=WidgetQuery)
    options: WidgetOptions = Field(default_factory=WidgetOptions)

    @model_validator(mode="after")
    def _validate_type_requirements(self) -> WidgetDefinition:
        """Reject a widget that cannot possibly render.

        Catching this at authoring time is the whole value: the
        alternative is a broken tile appearing on a shared dashboard
        with no explanation of what the author got wrong.
        """
        kind = self.widget_type
        if kind in CHART_TYPES and self.options.series is None:
            raise ValueError(f"Widget {self.widget_key!r}: a {kind} requires a series spec.")
        if kind in TABULAR_TYPES and not self.options.columns:
            raise ValueError(f"Widget {self.widget_key!r}: a {kind} requires columns.")
        if kind in (WidgetType.METRIC_CARD, WidgetType.GAUGE) and self.options.metric is None:
            raise ValueError(f"Widget {self.widget_key!r}: a {kind} requires a metric spec.")
        if kind is WidgetType.GAUGE and not self.options.thresholds:
            raise ValueError(f"Widget {self.widget_key!r}: a gauge requires thresholds.")
        if kind is WidgetType.TOPOLOGY_GRAPH and self.options.topology is None:
            raise ValueError(f"Widget {self.widget_key!r}: a topology graph requires a spec.")
        if kind is WidgetType.MARKDOWN and not self.options.content:
            raise ValueError(f"Widget {self.widget_key!r}: a markdown widget requires content.")
        if kind is WidgetType.AI_INSIGHT and not self.options.ai_prompt:
            raise ValueError(f"Widget {self.widget_key!r}: an AI widget requires a prompt.")
        if kind is WidgetType.HEATMAP and len(self.options.columns) < 1:
            raise ValueError(f"Widget {self.widget_key!r}: a heatmap requires columns.")

        needs_data = kind not in STATIC_TYPES and kind is not WidgetType.AI_INSIGHT
        if needs_data and self.query.source is DataSource.STATIC:
            raise ValueError(
                f"Widget {self.widget_key!r}: a {kind} needs a data source, not 'static'."
            )
        return self


def parse_widget(raw: dict[str, Any]) -> WidgetDefinition:
    """Parse and validate one authored widget.

    Raises:
        ValidationError: Pydantic's own, which callers convert to the
            platform's ``ValidationError`` at the boundary rather than
            leaking a library type outward.
    """
    return WidgetDefinition.model_validate(raw)


def parse_options(raw: dict[str, Any]) -> WidgetOptions:
    """Parse a stored options blob on its own."""
    return WidgetOptions.model_validate(raw)


def parse_query(raw: dict[str, Any]) -> WidgetQuery:
    """Parse a stored query blob on its own."""
    return WidgetQuery.model_validate(raw)


__all__ = [
    "CHART_TYPES",
    "FEED_TYPES",
    "STATIC_TYPES",
    "TABULAR_TYPES",
    "ColumnSpec",
    "MetricSpec",
    "SeriesSpec",
    "Threshold",
    "TopologySpec",
    "WidgetDefinition",
    "WidgetOptions",
    "WidgetQuery",
    "parse_options",
    "parse_query",
    "parse_widget",
]
