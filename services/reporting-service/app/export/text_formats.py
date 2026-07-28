"""CSV, JSON, Markdown, HTML, and XML exporters.

The five text formats live together because they share one concern --
escaping -- and getting that wrong is the entire risk here. Each uses
the standard library's own escaping (``csv``, ``json``, ``html``,
``xml.sax.saxutils``) rather than hand-rolled string replacement, so a
report containing ``</td>``, a quote, or an ampersand produces a valid
document instead of a corrupted or injectable one.
"""

from __future__ import annotations

import csv
import html
import io
import json
from xml.sax.saxutils import escape as xml_escape
from xml.sax.saxutils import quoteattr

from app.models.enums import SectionKind
from app.renderer.document import RenderedReport, RenderedSection

_THEMES: dict[str, tuple[str, str]] = {
    "slate": ("#1f2937", "#f3f4f6"),
    "ocean": ("#0f4c81", "#e8f1f8"),
    "forest": ("#14532d", "#e9f5ec"),
    "plum": ("#4c1d95", "#f1ebfb"),
}
"""Theme name to (header colour, zebra-stripe colour).

Kept as data rather than CSS files so the PDF renderer, which cannot
parse CSS, uses the same palette as the HTML one.
"""


def theme_colors(theme: str) -> tuple[str, str]:
    """Return a theme's colours, falling back to ``slate``.

    An unknown theme name is a cosmetic problem, never a reason to fail
    a report that is otherwise correct.
    """
    return _THEMES.get(theme, _THEMES["slate"])


def _tabular_sections(report: RenderedReport) -> list[RenderedSection]:
    """Sections that carry rows, in order."""
    return [section for section in report.sections if section.rows and section.columns]


def to_csv(report: RenderedReport) -> bytes:
    """Serialise every table section to one CSV document.

    Multiple table sections are separated by a blank line and a
    ``# <title>`` marker. A single flat CSV would silently interleave
    rows with different column sets, which is worse than a document a
    reader can visibly segment.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    sections = _tabular_sections(report)

    if not sections:
        writer.writerow([report.title])
        writer.writerow(["generated_at", report.generated_at.isoformat()])
        return buffer.getvalue().encode("utf-8")

    for index, section in enumerate(sections):
        if index:
            writer.writerow([])
        if len(sections) > 1:
            writer.writerow([f"# {section.title or section.key}"])
        writer.writerow([column.label for column in section.columns])
        writer.writerows(section.cell_values())
    return buffer.getvalue().encode("utf-8")


def to_json(report: RenderedReport) -> bytes:
    """Serialise the whole report as JSON."""
    return json.dumps(report.as_dict(), indent=2, default=str).encode("utf-8")


def to_markdown(report: RenderedReport) -> bytes:
    """Serialise the report as Markdown."""
    lines: list[str] = [f"# {report.title}", ""]
    if report.subtitle:
        lines += [f"_{report.subtitle}_", ""]
    lines += [
        f"Generated {report.generated_at.isoformat()} by {report.branding.company_name}.",
        "",
    ]

    for section in report.sections:
        if section.title:
            lines += [f"## {section.title}", ""]
        if section.error:
            lines += [f"> **Section unavailable:** {section.error}", ""]
            continue
        if section.kind is SectionKind.PAGE_BREAK:
            lines += ["---", ""]
            continue
        if section.text:
            lines += [section.text, ""]
        if section.metric_value is not None:
            label = section.metric_label or section.key
            lines += [f"**{label}:** {_format_number(section.metric_value)}", ""]
        if section.chart_points:
            for label, value in section.chart_points:
                lines.append(f"- {label}: {_format_number(value)}")
            lines.append("")
        if section.rows and section.columns:
            header = " | ".join(_md_escape(c.label) for c in section.columns)
            divider = " | ".join("---" for _ in section.columns)
            lines += [f"| {header} |", f"| {divider} |"]
            lines += [
                "| " + " | ".join(_md_escape(cell) for cell in row) + " |"
                for row in section.cell_values()
            ]
            lines.append("")
    return "\n".join(lines).encode("utf-8")


def _md_escape(text: str) -> str:
    """Escape pipes and newlines so one cell cannot break the table."""
    return text.replace("|", "\\|").replace("\n", " ")


def _format_number(value: float) -> str:
    """Render a metric without a pointless trailing ``.0``."""
    return str(int(value)) if float(value).is_integer() else f"{value:,.2f}"


def to_html(report: RenderedReport) -> bytes:
    """Serialise the report as a self-contained HTML document.

    Every interpolated value goes through :func:`html.escape`, so a row
    containing markup renders as text rather than executing.
    """
    header_color, stripe_color = theme_colors(report.branding.theme)
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{html.escape(report.title)}</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:2rem;color:#111}",
        "table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:14px}",
        f"th{{background:{header_color};color:#fff;text-align:left;padding:8px}}",
        "td{padding:8px;border-bottom:1px solid #ddd}",
        f"tr:nth-child(even) td{{background:{stripe_color}}}",
        ".metric{font-size:2rem;font-weight:600}",
        ".error{padding:12px;border-left:4px solid #b91c1c;background:#fef2f2}",
        ".bar{background:" + header_color + ";height:14px;display:inline-block}",
        "footer{margin-top:2rem;color:#666;font-size:12px}",
        "</style></head><body>",
        f"<h1>{html.escape(report.title)}</h1>",
    ]
    if report.subtitle:
        parts.append(f"<p><em>{html.escape(report.subtitle)}</em></p>")
    parts.append(
        f"<p>Generated {html.escape(report.generated_at.isoformat())} by "
        f"{html.escape(report.branding.company_name)}.</p>"
    )

    for section in report.sections:
        if section.title:
            parts.append(f"<h2>{html.escape(section.title)}</h2>")
        if section.error:
            parts.append(
                f'<div class="error">Section unavailable: {html.escape(section.error)}</div>'
            )
            continue
        if section.kind is SectionKind.PAGE_BREAK:
            parts.append("<hr>")
            continue
        if section.text:
            parts.append(f"<p>{html.escape(section.text)}</p>")
        if section.metric_value is not None:
            label = html.escape(section.metric_label or section.key)
            parts.append(
                f'<p><span class="metric">{html.escape(_format_number(section.metric_value))}'
                f"</span><br>{label}</p>"
            )
        if section.chart_points:
            parts.append(_html_chart(section))
        if section.rows and section.columns:
            head = "".join(f"<th>{html.escape(c.label)}</th>" for c in section.columns)
            body = "".join(
                "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
                for row in section.cell_values()
            )
            parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")

    if report.branding.footer_text:
        parts.append(f"<footer>{html.escape(report.branding.footer_text)}</footer>")
    parts.append("</body></html>")
    return "\n".join(parts).encode("utf-8")


def _html_chart(section: RenderedSection) -> str:
    """Render chart points as inline proportional bars.

    Plain HTML/CSS rather than an embedded charting library: the output
    has to render in an email client and in any browser with no network
    access, which rules out a script-driven chart.
    """
    largest = max((value for _label, value in section.chart_points), default=0.0)
    rows: list[str] = ["<table>"]
    for label, value in section.chart_points:
        width = 0 if largest <= 0 else max(1, round(value / largest * 240))
        rows.append(
            f"<tr><td>{html.escape(label)}</td>"
            f'<td><span class="bar" style="width:{width}px"></span> '
            f"{html.escape(_format_number(value))}</td></tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def to_xml(report: RenderedReport) -> bytes:
    """Serialise the report as XML.

    Element *names* come from fixed literals and column keys; a column
    key that is not a valid XML name is emitted as a generic ``<cell>``
    with a ``key`` attribute rather than producing malformed XML.
    """
    parts: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>', "<report>"]
    parts.append(f"  <title>{xml_escape(report.title)}</title>")
    if report.subtitle:
        parts.append(f"  <subtitle>{xml_escape(report.subtitle)}</subtitle>")
    parts.append(f"  <generatedAt>{xml_escape(report.generated_at.isoformat())}</generatedAt>")
    parts.append(f"  <company>{xml_escape(report.branding.company_name)}</company>")

    parts.append("  <sections>")
    for section in report.sections:
        parts.append(
            f"    <section key={quoteattr(section.key)} " f"kind={quoteattr(str(section.kind))}>"
        )
        if section.title:
            parts.append(f"      <title>{xml_escape(section.title)}</title>")
        if section.error:
            parts.append(f"      <error>{xml_escape(section.error)}</error>")
        if section.text:
            parts.append(f"      <text>{xml_escape(section.text)}</text>")
        if section.metric_value is not None:
            parts.append(f"      <metric>{xml_escape(str(section.metric_value))}</metric>")
        for label, value in section.chart_points:
            parts.append(f"      <point label={quoteattr(label)}>{xml_escape(str(value))}</point>")
        if section.rows and section.columns:
            parts.append("      <rows>")
            for row in section.cell_values():
                parts.append("        <row>")
                for column, cell in zip(section.columns, row, strict=True):
                    parts.append(f"          {_xml_cell(column.key, cell)}")
                parts.append("        </row>")
            parts.append("      </rows>")
        parts.append("    </section>")
    parts.append("  </sections>")
    parts.append("</report>")
    return "\n".join(parts).encode("utf-8")


def _xml_cell(key: str, value: str) -> str:
    """Emit one cell, degrading to ``<cell key="...">`` for odd keys."""
    if key.isidentifier():
        return f"<{key}>{xml_escape(value)}</{key}>"
    return f"<cell key={quoteattr(key)}>{xml_escape(value)}</cell>"


__all__ = [
    "theme_colors",
    "to_csv",
    "to_html",
    "to_json",
    "to_markdown",
    "to_xml",
]
