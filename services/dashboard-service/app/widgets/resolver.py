"""The widget resolver -- turns definitions into rendered payloads.

For one dashboard load:

1. Fetch every widget's data source **concurrently** (bounded).
2. Apply dashboard-wide and per-widget filters.
3. Reduce rows into the shape the widget type needs -- a metric, a
   series, a table, a feed, a graph, or AI prose.

**A failing widget degrades; it does not fail the dashboard.** One
unreachable source marks its own tile ``FAILED`` with the reason, and
every other widget still renders. A dashboard is the thing an operator
looks at during an incident, so losing all of it because one source is
down is precisely the wrong failure mode.

**Concurrency is network-only and bounded.** Data-source fetches are
HTTP and safe to overlap under a semaphore. No database work happens
here -- an ``AsyncSession`` is not safe for concurrent use even for
reads, the rule every AI-IOS service has followed since
``services/validation-service``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.clients.platform import PlatformSourceClient
from app.filters.engine import FilterClause, apply_filters
from app.models.dashboard_widget import DashboardWidget
from app.models.enums import DataSource, TopologyQueryKind, WidgetStatus, WidgetType
from app.topology.graph import TopologyReader
from app.widgets.schema import (
    CHART_TYPES,
    FEED_TYPES,
    TABULAR_TYPES,
    WidgetOptions,
    WidgetQuery,
    parse_options,
    parse_query,
)

logger = get_logger("app.widgets.resolver")

_OTHER_LABEL = "Other"

WidgetShape = Callable[[list[dict[str, Any]], "WidgetOptions", "WidgetType"], dict[str, Any]]
"""Builds one widget type's payload from its filtered rows."""


@dataclass(slots=True)
class ResolvedWidget:
    """One widget, resolved and ready to send to a client."""

    widget_key: str
    widget_type: WidgetType
    title: str
    status: WidgetStatus = WidgetStatus.OK
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    row_count: int = 0
    duration_ms: float | None = None

    @property
    def failed(self) -> bool:
        """Whether this widget could not be resolved."""
        return self.status is WidgetStatus.FAILED

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response or stream frame."""
        return {
            "widget_key": self.widget_key,
            "widget_type": str(self.widget_type),
            "title": self.title,
            "status": str(self.status),
            "payload": self.payload,
            "error": self.error,
            "row_count": self.row_count,
            "duration_ms": self.duration_ms,
        }


def _numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    """Every genuinely numeric value of *key*, in row order.

    Non-numeric values are skipped rather than coerced to zero, and
    booleans are excluded outright: ``True`` is not the number 1 in a
    metric column, and treating it as one silently skews an average.
    """
    numbers: list[float] = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, bool) or value is None:
            continue
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    return numbers


_REDUCERS: dict[str, Callable[[list[float]], float]] = {
    "sum": sum,
    "avg": lambda numbers: sum(numbers) / len(numbers),
    "min": min,
    "max": max,
    "latest": lambda numbers: numbers[-1],
}
"""Aggregate name to its reducer, applied to non-empty numeric lists."""


def aggregate(rows: list[dict[str, Any]], key: str | None, how: str) -> float:
    """Reduce rows to a single number."""
    if how == "count":
        return float(len(rows))
    if not key:
        return 0.0
    numbers = _numeric_values(rows, key)
    reducer = _REDUCERS.get(how)
    if not numbers or reducer is None:
        return 0.0
    return float(reducer(numbers))


def build_series(
    rows: list[dict[str, Any]], *, label_key: str, value_key: str, how: str, max_points: int
) -> list[dict[str, Any]]:
    """Group rows into a plotted series, largest first.

    Categories beyond *max_points* are summed into a single "Other"
    entry rather than dropped, so the plotted total still equals the
    data's total. A chart that silently under-reports is a correctness
    bug, not a cosmetic one.
    """
    buckets: dict[str, list[float]] = {}
    for row in rows:
        label = str(row.get(label_key, "")) or "(none)"
        raw = row.get(value_key)
        if how == "count" or raw is None:
            buckets.setdefault(label, []).append(1.0)
            continue
        try:
            buckets.setdefault(label, []).append(float(raw))
        except (TypeError, ValueError):
            buckets.setdefault(label, []).append(1.0)

    reducer = _REDUCERS.get(how, sum)
    totals = [
        (label, float(len(values)) if how == "count" else float(reducer(values)))
        for label, values in buckets.items()
    ]
    totals.sort(key=lambda item: item[1], reverse=True)

    if len(totals) > max_points:
        head = totals[: max_points - 1]
        tail_total = sum(value for _label, value in totals[max_points - 1 :])
        totals = [*head, (_OTHER_LABEL, tail_total)]
    return [{"label": label, "value": value} for label, value in totals]


def resolve_threshold(options: WidgetOptions, value: float) -> dict[str, Any] | None:
    """The band a gauge value falls into, or ``None`` below the lowest.

    Bands are sorted ascending on validation, so the last band whose
    lower bound the value meets is the right one.
    """
    matched: dict[str, Any] | None = None
    for band in options.thresholds:
        if value >= band.at:
            matched = {"at": band.at, "color": band.color, "label": band.label}
    return matched


def _build_metric(
    rows: list[dict[str, Any]], options: WidgetOptions, widget_type: WidgetType
) -> dict[str, Any]:
    """A metric card or gauge: one number, optionally banded."""
    spec = options.metric
    value = aggregate(rows, spec.value_key if spec else None, spec.aggregate if spec else "count")
    payload: dict[str, Any] = {
        "value": round(value, spec.precision if spec else 0),
        "unit": spec.unit if spec else None,
    }
    if widget_type is WidgetType.GAUGE:
        payload["threshold"] = resolve_threshold(options, value)
        payload["bands"] = [
            {"at": band.at, "color": band.color, "label": band.label} for band in options.thresholds
        ]
    return payload


def _build_chart(
    rows: list[dict[str, Any]], options: WidgetOptions, _widget_type: WidgetType
) -> dict[str, Any]:
    """A plotted series."""
    spec = options.series
    assert spec is not None
    return {
        "series": build_series(
            rows,
            label_key=spec.label_key,
            value_key=spec.value_key,
            how=spec.aggregate,
            max_points=spec.max_points,
        ),
        "stacked": options.stacked,
        "show_legend": options.show_legend,
    }


def _build_table(
    rows: list[dict[str, Any]], options: WidgetOptions, _widget_type: WidgetType
) -> dict[str, Any]:
    """Rows and columns, truncated visibly rather than silently."""
    return {
        "columns": [
            {"key": column.key, "label": column.label, "align": column.align}
            for column in options.columns
        ],
        "rows": rows[: options.limit],
        "truncated": len(rows) > options.limit,
    }


def _build_feed(
    rows: list[dict[str, Any]], options: WidgetOptions, _widget_type: WidgetType
) -> dict[str, Any]:
    """A reverse-chronological list."""
    return {"items": rows[: options.limit], "truncated": len(rows) > options.limit}


def _build_raw(
    rows: list[dict[str, Any]], options: WidgetOptions, _widget_type: WidgetType
) -> dict[str, Any]:
    """Unshaped rows, for ``CUSTOM`` and anything newly added.

    Handing the rows back unshaped is deliberate: guessing a shape for
    a widget type this service does not understand would produce a
    confidently wrong payload, where a bespoke client can render the
    rows correctly.
    """
    return {"rows": rows[: options.limit]}


_SHAPES: tuple[tuple[frozenset[WidgetType], WidgetShape], ...] = (
    (frozenset({WidgetType.METRIC_CARD, WidgetType.GAUGE}), _build_metric),
    (CHART_TYPES, _build_chart),
    (TABULAR_TYPES | frozenset({WidgetType.HEATMAP}), _build_table),
    (FEED_TYPES, _build_feed),
)
"""Widget types to the builder that shapes their payload.

A table rather than a branch chain, so a newly added type that nobody
wired up falls through to :func:`_build_raw` visibly instead of
silently taking another type's shape.
"""


def _shape_for(widget_type: WidgetType) -> WidgetShape:
    """The payload builder for *widget_type*."""
    for types, builder in _SHAPES:
        if widget_type in types:
            return builder
    return _build_raw


class WidgetResolver:
    """Resolves dashboard widgets into rendered payloads."""

    def __init__(
        self,
        sources: PlatformSourceClient | None,
        topology: TopologyReader | None = None,
        ai_client: Any | None = None,
        *,
        max_parallel: int = 6,
        max_rows: int = 5_000,
        anonymous: bool = False,
    ) -> None:
        self._sources = sources
        self._topology = topology
        self._ai = ai_client
        self._max_parallel = max_parallel
        self._max_rows = max_rows
        self._anonymous = anonymous or sources is None

    async def resolve_many(
        self,
        widgets: list[DashboardWidget],
        *,
        organization_id: UUID,
        dashboard_filters: list[FilterClause] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> list[ResolvedWidget]:
        """Resolve every widget concurrently, bounded by a semaphore.

        Returned in the same order as *widgets* so the caller does not
        have to re-sort a dashboard it already ordered.
        """
        if not widgets:
            return []
        semaphore = asyncio.Semaphore(self._max_parallel)

        async def _bounded(widget: DashboardWidget) -> ResolvedWidget:
            async with semaphore:
                return await self.resolve(
                    widget,
                    organization_id=organization_id,
                    dashboard_filters=dashboard_filters,
                    parameters=parameters,
                )

        return list(await asyncio.gather(*(_bounded(widget) for widget in widgets)))

    async def resolve(
        self,
        widget: DashboardWidget,
        *,
        organization_id: UUID,
        dashboard_filters: list[FilterClause] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> ResolvedWidget:
        """Resolve one widget. Never raises.

        Every failure becomes a ``FAILED`` tile carrying its reason,
        because a dashboard that renders nineteen widgets and one error
        message is far more useful than one that renders nothing.
        """
        started = time.monotonic()
        widget_type = (
            widget.widget_type
            if isinstance(widget.widget_type, WidgetType)
            else WidgetType(widget.widget_type)
        )
        resolved = ResolvedWidget(
            widget_key=widget.widget_key, widget_type=widget_type, title=widget.title
        )
        if self._anonymous:
            # An anonymous viewer -- someone holding only a share link --
            # has no credential to read the source services with, and
            # this service holds none of its own. Returning the widget's
            # shape with an explicit UNAUTHORIZED status is honest;
            # resolving it under somebody else's rights would not be.
            resolved.status = WidgetStatus.UNAUTHORIZED
            resolved.error = (
                "Sign in to see this widget's data. A share link opens the "
                "dashboard's layout, not the data behind it."
            )
            resolved.duration_ms = (time.monotonic() - started) * 1000
            return resolved
        try:
            options = parse_options(widget.options)
            query = parse_query(widget.query)
            payload, rows = await self._resolve_payload(
                widget,
                widget_type,
                query,
                options,
                organization_id=organization_id,
                dashboard_filters=dashboard_filters or [],
                parameters=parameters or {},
            )
            resolved.payload = payload
            resolved.row_count = rows
            if not payload:
                resolved.status = WidgetStatus.EMPTY
        except DependencyError as exc:
            resolved.status = WidgetStatus.FAILED
            resolved.error = str(exc)
            logger.warning(
                "Widget data source failed.",
                extra={"extra_fields": {"widget": widget.widget_key, "error": str(exc)}},
            )
        except ValidationError as exc:
            resolved.status = WidgetStatus.FAILED
            resolved.error = str(exc)
        except Exception as exc:
            resolved.status = WidgetStatus.FAILED
            resolved.error = f"Widget could not be rendered: {exc}"
            logger.warning(
                "Widget resolution raised unexpectedly.",
                extra={"extra_fields": {"widget": widget.widget_key, "error": str(exc)}},
            )
        resolved.duration_ms = (time.monotonic() - started) * 1000
        return resolved

    async def _fetch_rows(
        self,
        query: WidgetQuery,
        *,
        widget_filters: list[dict[str, Any]],
        dashboard_filters: list[FilterClause],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Fetch and filter one widget's rows."""
        if query.source is DataSource.STATIC or self._sources is None:
            return []
        params = {**{k: str(v) for k, v in parameters.items()}, **query.params}
        rows = await self._sources.fetch(
            query.source, query.path, params=params, result_path=query.result_path
        )
        clauses = [*dashboard_filters, *_parse_widget_filters(widget_filters)]
        filtered = apply_filters(rows, clauses)
        if len(filtered) > self._max_rows:
            raise DependencyError(
                f"Widget matched {len(filtered):,} rows, above the "
                f"{self._max_rows:,}-row ceiling. Narrow its filters."
            )
        return filtered

    async def _resolve_payload(
        self,
        widget: DashboardWidget,
        widget_type: WidgetType,
        query: WidgetQuery,
        options: WidgetOptions,
        *,
        organization_id: UUID,
        dashboard_filters: list[FilterClause],
        parameters: dict[str, Any],
    ) -> tuple[dict[str, Any], int]:
        """Build the payload for one widget type.

        The three types that need no rows are handled first; everything
        else fetches once and then hands off to a per-shape builder, so
        adding a widget type means adding one table entry rather than
        another branch in a growing chain.
        """
        if widget_type is WidgetType.MARKDOWN:
            return {"content": options.content or ""}, 0
        if widget_type is WidgetType.TOPOLOGY_GRAPH:
            return await self._resolve_topology(options, organization_id, parameters), 0
        if widget_type is WidgetType.AI_INSIGHT:
            return await self._resolve_ai(options, organization_id), 0

        rows = await self._fetch_rows(
            query,
            widget_filters=widget.filters,
            dashboard_filters=dashboard_filters,
            parameters=parameters,
        )
        builder = _shape_for(widget_type)
        return builder(rows, options, widget_type), len(rows)

    async def _resolve_topology(
        self, options: WidgetOptions, organization_id: UUID, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve a topology widget through Neo4j."""
        spec = options.topology
        assert spec is not None
        if self._topology is None or not self._topology.enabled:
            raise DependencyError("Topology visualisation is not configured on this deployment.")
        root_id = str(parameters.get(spec.root_key, "")).strip()
        if not root_id:
            raise ValidationError(
                f"This topology widget needs a {spec.root_key!r} parameter to start from."
            )
        kind = (
            spec.kind if isinstance(spec.kind, TopologyQueryKind) else TopologyQueryKind(spec.kind)
        )
        graph = await self._topology.query(
            organization_id=str(organization_id),
            root_id=root_id,
            kind=kind,
            depth=spec.depth,
        )
        return graph.as_dict()

    async def _resolve_ai(self, options: WidgetOptions, organization_id: UUID) -> dict[str, Any]:
        """Resolve an AI insight widget through Prompt 046."""
        if self._ai is None or not getattr(self._ai, "enabled", False):
            raise DependencyError("AI insights are not configured on this deployment.")
        summary = await self._ai.summarise(
            organization_id=organization_id, instruction=options.ai_prompt or ""
        )
        return {"text": summary.text, "citations": summary.citations}


def _parse_widget_filters(raw: list[dict[str, Any]]) -> list[FilterClause]:
    """Parse a widget's own stored filter clauses."""
    return [FilterClause.from_dict(entry) for entry in raw]


__all__ = [
    "ResolvedWidget",
    "WidgetResolver",
    "aggregate",
    "build_series",
    "resolve_threshold",
]
