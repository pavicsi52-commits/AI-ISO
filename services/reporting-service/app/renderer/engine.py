"""The rendering engine -- resolves a designer document into data.

Flow for one report:

1. Bind parameters to their declared types.
2. Fetch every section's data source **concurrently** (bounded).
3. Apply filters to each section's rows.
4. Compute metrics and chart series.
5. Generate AI narratives.
6. Assemble a :class:`~app.renderer.document.RenderedReport`.

**Concurrency is network-only and bounded.** Data-source fetches are
HTTP and genuinely safe to overlap, so they run under a semaphore. No
database work happens here at all -- an ``AsyncSession`` is not safe for
concurrent use even for reads, the rule every AI-IOS service has
followed since ``services/validation-service``. Persistence is the
caller's job, sequentially.

**A failing section degrades, it does not abort.** One unreachable
source marks its own section unavailable and the report still renders.
An infrastructure report delivered with a visible gap is far more
useful than nothing at all, and the gap is recorded on the section so
neither the reader nor the operator has to guess.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.ai.summaries import AiSummaryClient, build_context
from app.clients.platform import PlatformSourceClient
from app.filters.engine import FilterClause, apply_filters
from app.models.enums import SectionKind
from app.parameters.binding import BoundParameters
from app.renderer.document import RenderedColumn, RenderedReport, RenderedSection
from app.reports.designer.schema import ReportDefinition, ReportSection

logger = get_logger("app.renderer.engine")

_environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
"""Sandboxed Jinja2 for section text.

A template is user-authored content, so rendering it with an
unrestricted environment would be a real injection path into whatever
the template can reach. ``autoescape`` is off because this produces
plain text, not HTML -- each *exporter* escapes for its own format,
which is the only place that knows the right escaping rules.
"""

_OTHER_LABEL = "Other"


def render_text(template: str, values: dict[str, Any]) -> str:
    """Render section text against bound parameters.

    An undefined variable raises rather than rendering empty:
    a sentence that silently loses its subject is worse than a loud
    authoring error.

    Raises:
        ValidationError: If the text references something unavailable
            or is not valid Jinja2.
    """
    try:
        return _environment.from_string(template).render(**values)
    except Exception as exc:
        raise ValidationError(f"Section text failed to render: {exc}") from exc


_AGGREGATES: dict[str, Callable[[list[float]], float]] = {
    "sum": sum,
    "avg": lambda numbers: sum(numbers) / len(numbers),
    "min": min,
    "max": max,
}
"""Aggregate name to its reducer, applied to non-empty numeric lists."""


def _numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    """Every genuinely numeric value of *key*, in row order.

    Non-numeric values are skipped rather than coerced to zero: a
    column with three numbers and one ``"n/a"`` should average the
    three, not be dragged toward zero by a value that is not a number.
    Booleans are excluded too -- ``True`` is not the number 1 here.
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


def _aggregate(rows: list[dict[str, Any]], key: str | None, how: str) -> float:
    """Compute one metric over *rows*."""
    if how == "count":
        return float(len(rows))
    if not key:
        return 0.0
    numbers = _numeric_values(rows, key)
    reducer = _AGGREGATES.get(how)
    if not numbers or reducer is None:
        return 0.0
    return float(reducer(numbers))


def _chart_series(
    rows: list[dict[str, Any]], label_key: str, value_key: str, max_slices: int
) -> list[tuple[str, float]]:
    """Aggregate rows into labelled magnitudes, largest first.

    Categories beyond *max_slices* are summed into a single "Other"
    entry rather than dropped, so the chart's total still equals the
    data's total -- a truncated chart that silently under-reports is a
    correctness bug, not a cosmetic one.
    """
    totals: dict[str, float] = {}
    for row in rows:
        label = str(row.get(label_key, "")) or "(none)"
        raw = row.get(value_key)
        if raw is None:
            value = 1.0
        else:
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = 1.0
        totals[label] = totals.get(label, 0.0) + value

    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    if len(ordered) <= max_slices:
        return ordered
    head = ordered[: max_slices - 1]
    tail_total = sum(value for _label, value in ordered[max_slices - 1 :])
    return [*head, (_OTHER_LABEL, tail_total)]


class ReportRenderer:
    """Resolves a report definition into a rendered document."""

    def __init__(
        self,
        sources: PlatformSourceClient,
        ai_client: AiSummaryClient | None = None,
        *,
        max_parallel_sections: int = 4,
        max_rows: int = 50_000,
    ) -> None:
        self._sources = sources
        self._ai = ai_client
        self._max_parallel = max_parallel_sections
        self._max_rows = max_rows

    async def _fetch_section(
        self, section: ReportSection, parameters: BoundParameters
    ) -> tuple[str, list[dict[str, Any]] | None, str | None]:
        """Fetch one section's rows; never raises.

        Returns ``(key, rows, error)`` so the caller can gather results
        without one failure cancelling its siblings.
        """
        if section.query is None:
            return section.key, [], None
        params = {**parameters.as_query_params(), **section.query.params}
        try:
            rows = await self._sources.fetch(
                section.query.source,
                section.query.path,
                params=params,
                result_path=section.query.result_path,
            )
        except (DependencyError, ValidationError) as exc:
            logger.warning(
                "Report section data source failed.",
                extra={"extra_fields": {"section": section.key, "error": str(exc)}},
            )
            return section.key, None, str(exc)
        return section.key, rows, None

    async def _fetch_all(
        self, definition: ReportDefinition, parameters: BoundParameters
    ) -> dict[str, tuple[list[dict[str, Any]] | None, str | None]]:
        """Fetch every section's data concurrently, bounded."""
        querying = [section for section in definition.sections if section.query is not None]
        if not querying:
            return {}

        semaphore = asyncio.Semaphore(self._max_parallel)

        async def _bounded(
            section: ReportSection,
        ) -> tuple[str, list[dict[str, Any]] | None, str | None]:
            async with semaphore:
                return await self._fetch_section(section, parameters)

        results = await asyncio.gather(*(_bounded(section) for section in querying))
        return {key: (rows, error) for key, rows, error in results}

    async def render(
        self,
        definition: ReportDefinition,
        *,
        organization_id: UUID,
        parameters: BoundParameters,
        filters: list[FilterClause] | None = None,
        project_id: UUID | None = None,
    ) -> RenderedReport:
        """Resolve *definition* into a rendered report.

        Raises:
            ValidationError: If section text or a filter is malformed.
                Data-source failures are *not* raised -- they mark
                their own section unavailable.
        """
        fetched = await self._fetch_all(definition, parameters)
        clauses = filters or []
        sections: list[RenderedSection] = []

        for section in definition.sections:
            rendered = await self._render_section(
                section,
                fetched.get(section.key, ([], None)),
                parameters=parameters,
                clauses=clauses,
                organization_id=organization_id,
                project_id=project_id,
            )
            sections.append(rendered)

        return RenderedReport(
            title=render_text(definition.title, parameters.values),
            subtitle=(
                render_text(definition.subtitle, parameters.values) if definition.subtitle else None
            ),
            branding=definition.branding,
            sections=sections,
            generated_at=datetime.now(UTC),
            parameters=dict(parameters.values),
        )

    async def _render_section(
        self,
        section: ReportSection,
        fetched: tuple[list[dict[str, Any]] | None, str | None],
        *,
        parameters: BoundParameters,
        clauses: list[FilterClause],
        organization_id: UUID,
        project_id: UUID | None,
    ) -> RenderedSection:
        """Resolve one section into its rendered form."""
        rows, error = fetched
        title = render_text(section.title, parameters.values) if section.title else None
        rendered = RenderedSection(key=section.key, kind=section.kind, title=title)

        if error is not None:
            rendered.error = error
            return rendered

        filtered = apply_filters(rows or [], clauses) if rows else []
        if len(filtered) > self._max_rows:
            rendered.error = (
                f"{len(filtered):,} rows exceed the {self._max_rows:,}-row ceiling; "
                "narrow the report's filters."
            )
            return rendered

        if section.text:
            rendered.text = render_text(section.text, parameters.values)

        match section.kind:
            case SectionKind.TABLE:
                rendered.columns = [
                    RenderedColumn(key=column.key, label=column.label, width=column.width)
                    for column in section.columns
                ]
                rendered.rows = filtered
            case SectionKind.METRIC:
                rendered.metric_value = _aggregate(
                    filtered, section.metric_key, section.metric_aggregate
                )
                rendered.metric_label = title or section.key
            case SectionKind.CHART if section.chart is not None:
                rendered.chart_kind = section.chart.kind
                rendered.chart_points = _chart_series(
                    filtered,
                    section.chart.label_key,
                    section.chart.value_key,
                    section.chart.max_slices,
                )
            case SectionKind.AI_SUMMARY:
                await self._render_ai_section(
                    rendered,
                    section,
                    filtered,
                    organization_id=organization_id,
                    project_id=project_id,
                )

        return rendered

    async def _render_ai_section(
        self,
        rendered: RenderedSection,
        section: ReportSection,
        rows: list[dict[str, Any]],
        *,
        organization_id: UUID,
        project_id: UUID | None,
    ) -> None:
        """Generate an AI narrative, degrading rather than failing."""
        if self._ai is None or not self._ai.enabled:
            rendered.error = "AI reporting is not configured on this deployment."
            return
        instruction = section.ai_prompt or section.text or "Summarise the supplied data."
        try:
            summary = await self._ai.summarise(
                organization_id=organization_id,
                instruction=instruction,
                context=build_context(rows),
                project_id=project_id,
            )
        except DependencyError as exc:
            logger.warning(
                "AI report section failed.",
                extra={"extra_fields": {"section": section.key, "error": str(exc)}},
            )
            rendered.error = str(exc)
            return
        rendered.text = summary.text
        if summary.citations:
            rendered.columns = [
                RenderedColumn(key="title", label="Source"),
                RenderedColumn(key="score", label="Relevance"),
            ]
            rendered.rows = [
                {"title": entry.get("title", ""), "score": entry.get("score", "")}
                for entry in summary.citations
            ]


__all__ = ["ReportRenderer", "render_text"]
