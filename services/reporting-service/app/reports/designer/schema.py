"""The report designer document ("REPORT DESIGNER").

A template's ``definition`` column holds one :class:`ReportDefinition`
serialised as JSON. Modelling it with Pydantic rather than storing an
unvalidated blob is what makes the JSON column honest: a malformed
designer document is rejected at write time with a precise error,
instead of blowing up hours later inside a scheduled render that
nobody is watching.

**Why JSON rather than tables.** The designer supports reusable
sections, widgets, charts, and themes whose shape is authored per
template. Normalising that into relational tables would force a schema
migration every time the designer gains a section kind, and would make
"give me this template exactly as authored" a multi-table join. The
trade is that the database cannot enforce the inner structure -- which
is precisely why this module exists and why every write path goes
through it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import ChartKind, DataSource, SectionKind


class DataQuery(BaseModel):
    """Where one section's rows come from.

    ``path`` is relative to the source service's own base URL, so a
    template never hardcodes a host and stays portable between
    environments. ``CUSTOM_API`` is the single exception and requires
    an absolute URL, which :mod:`app.clients.platform` validates.
    """

    source: DataSource
    path: str = Field(min_length=1, max_length=1024)
    params: dict[str, Any] = Field(default_factory=dict)
    result_path: str | None = Field(default=None, max_length=255)
    """Dotted path into the response envelope, e.g. ``data.items``.

    Defaults to the platform's own ``data`` envelope key when omitted,
    which is what every AI-IOS service returns.
    """


class ColumnSpec(BaseModel):
    """One column of a table section."""

    key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=255)
    width: float | None = Field(default=None, gt=0)
    format: str | None = Field(default=None, max_length=32)
    """Optional value formatter: ``date``, ``datetime``, ``percent``,
    ``bytes``, or ``number``. Unknown formatters fall back to ``str``
    rather than raising -- a cosmetic mismatch must not fail a report.
    """


class ChartSpec(BaseModel):
    """How a chart section plots its data."""

    kind: ChartKind = ChartKind.BAR
    label_key: str = Field(min_length=1, max_length=128)
    value_key: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=255)
    max_slices: int = Field(default=12, ge=1, le=50)
    """Categories beyond this are grouped into "Other".

    A pie chart with 400 slices is unreadable; silently truncating
    would misreport totals, so the remainder is aggregated instead.
    """


class ReportSection(BaseModel):
    """One block of a report.

    Sections are the reusable unit docs/047 asks for: a section carries
    everything needed to render itself, so the same definition can be
    copied between templates without dragging along template-level
    state.
    """

    key: str = Field(min_length=1, max_length=64)
    kind: SectionKind
    title: str | None = Field(default=None, max_length=255)
    text: str | None = None
    """Static prose, or a Jinja2 template rendered against parameters."""

    query: DataQuery | None = None
    columns: list[ColumnSpec] = Field(default_factory=list)
    chart: ChartSpec | None = None
    metric_key: str | None = Field(default=None, max_length=128)
    metric_aggregate: Literal["count", "sum", "avg", "min", "max"] = "count"
    ai_prompt: str | None = None
    """Instruction for an ``AI_SUMMARY`` section, sent to Prompt 046."""

    @model_validator(mode="after")
    def _validate_kind_requirements(self) -> ReportSection:
        """Reject a section that cannot possibly render.

        Catching this at authoring time is the whole value: the
        alternative is a scheduled report failing at 03:00 because a
        table section was saved with no query.
        """
        if self.kind is SectionKind.TABLE:
            if self.query is None:
                raise ValueError(f"Section {self.key!r}: a table section requires a query.")
            if not self.columns:
                raise ValueError(f"Section {self.key!r}: a table section requires columns.")
        if self.kind is SectionKind.CHART:
            if self.query is None:
                raise ValueError(f"Section {self.key!r}: a chart section requires a query.")
            if self.chart is None:
                raise ValueError(f"Section {self.key!r}: a chart section requires a chart spec.")
        if self.kind is SectionKind.METRIC and self.query is None:
            raise ValueError(f"Section {self.key!r}: a metric section requires a query.")
        if (
            self.kind is SectionKind.METRIC
            and self.metric_aggregate != "count"
            and not self.metric_key
        ):
            raise ValueError(
                f"Section {self.key!r}: aggregate "
                f"{self.metric_aggregate!r} requires a metric_key."
            )
        if self.kind in (SectionKind.HEADING, SectionKind.TEXT) and not self.text:
            raise ValueError(f"Section {self.key!r}: a {self.kind} section requires text.")
        return self


class Branding(BaseModel):
    """Company branding applied to rendered output ("Branding")."""

    company_name: str = Field(default="AI-IOS", max_length=255)
    logo_data_uri: str | None = None
    """A ``data:`` URI rather than a URL.

    A renderer that fetched a remote logo would make report generation
    depend on an external host being up, and would leak a request to
    that host every time a report ran.
    """

    theme: str = Field(default="slate", max_length=32)
    footer_text: str | None = Field(default=None, max_length=512)
    show_page_numbers: bool = True
    show_table_of_contents: bool = True


class ReportDefinition(BaseModel):
    """A complete designer document."""

    title: str = Field(min_length=1, max_length=255)
    subtitle: str | None = Field(default=None, max_length=512)
    sections: list[ReportSection] = Field(default_factory=list)
    branding: Branding = Field(default_factory=Branding)

    @model_validator(mode="after")
    def _validate_unique_section_keys(self) -> ReportDefinition:
        """Section keys must be unique.

        Duplicates would make a rendered section impossible to
        reference unambiguously from history or an error message.
        """
        keys = [section.key for section in self.sections]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise ValueError(f"Duplicate section keys: {', '.join(duplicates)}.")
        return self

    def referenced_sources(self) -> list[DataSource]:
        """Every distinct data source this definition reads, in order."""
        seen: list[DataSource] = []
        for section in self.sections:
            if section.query is not None and section.query.source not in seen:
                seen.append(section.query.source)
        return seen


def parse_definition(raw: dict[str, Any]) -> ReportDefinition:
    """Parse and validate a stored designer document.

    Raises:
        ValidationError: If the document is malformed. Callers convert
            this to the platform's own ``ValidationError`` at the
            boundary rather than leaking Pydantic's type outward.
    """
    return ReportDefinition.model_validate(raw)


__all__ = [
    "Branding",
    "ChartSpec",
    "ColumnSpec",
    "DataQuery",
    "ReportDefinition",
    "ReportSection",
    "parse_definition",
]
