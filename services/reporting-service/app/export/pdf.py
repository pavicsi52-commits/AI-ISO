"""PDF export via ``reportlab`` ("PDF FEATURES").

Implements the doc's own list: headers, footers, page numbers, table of
contents, charts, images, company branding, digital signature, and
password protection.

Two of those need an honest note, and both are stated here rather than
implied to be more than they are:

- **Password protection** is real: ``reportlab``'s own
  :class:`~reportlab.lib.pdfencrypt.StandardEncryption` applies AES to
  the document. That is genuine PDF encryption, not a viewer hint.
- **Digital signature** is *not* a cryptographic PKCS#7 signature.
  ``reportlab`` cannot produce one, and no signing library is in this
  platform's dependency set. What is implemented is a visible signature
  block carrying the signer, timestamp, and a SHA-256 digest of the
  document body -- which lets a reader detect alteration, but is not a
  PKI signature and must not be described as one. Adding real signing
  means taking a dependency such as ``pyhanko``, which is a deliberate
  decision for whoever needs it.
"""

from __future__ import annotations

import hashlib
import io
from base64 import b64decode
from datetime import UTC, datetime
from typing import Any

from reportlab.lib import colors, pdfencrypt
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from shared_core.logging.logger import get_logger

from app.export.text_formats import theme_colors
from app.models.enums import SectionKind
from app.renderer.document import RenderedReport, RenderedSection

logger = get_logger("app.export.pdf")

_MAX_TABLE_ROWS = 2_000
"""Rows rendered into a PDF table before truncating with a notice.

``reportlab`` lays out every row in memory; tens of thousands of rows
turns one report into an out-of-memory event for the whole process.
Truncating *visibly* -- with a line stating how many rows were omitted
and pointing at CSV/XLSX -- is honest, where silently dropping them
would not be.
"""

_MAX_LOGO_BYTES = 2 * 1024 * 1024

_NEWLINE = "\n"
"""Section text is plain text; PDF paragraphs need explicit ``<br/>``."""


class _NumberedCanvas(Canvas):
    """Canvas that stamps "Page N of M" once the total is known.

    Page count is only knowable after the whole document is laid out,
    so pages are buffered and the footer drawn on a second pass. This
    is the standard ``reportlab`` idiom for the purpose.
    """

    def __init__(self, *args: Any, footer_text: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_pages: list[dict[str, Any]] = []
        self._footer_text = footer_text

    def showPage(self) -> None:  # noqa: N802  -- reportlab's own API name
        self._saved_pages.append(dict(self.__dict__))
        # ``_startPage``/``_pagesize`` are reportlab Canvas internals with
        # no stubs; this two-pass footer is that library's own documented
        # idiom for late-bound page totals.
        self._startPage()  # type: ignore[attr-defined]

    def save(self) -> None:
        total = len(self._saved_pages)
        for number, state in enumerate(self._saved_pages, start=1):
            self.__dict__.update(state)
            self._draw_footer(number, total)
            super().showPage()
        super().save()

    def _draw_footer(self, number: int, total: int) -> None:
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#666666"))
        width, _height = self._pagesize  # type: ignore[attr-defined]
        if self._footer_text:
            self.drawString(15 * mm, 10 * mm, self._footer_text[:120])
        self.drawRightString(width - 15 * mm, 10 * mm, f"Page {number} of {total}")


def _signature_digest(report: RenderedReport) -> str:
    """SHA-256 over the report's own resolved content.

    Computed from the rendered document rather than the PDF bytes,
    because the digest has to be embeddable *in* those bytes. It
    therefore attests to the report's data, which is what a reader
    checking for alteration actually cares about.
    """
    payload = repr(report.as_dict()).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _logo_flowable(data_uri: str) -> Image | None:
    """Decode a ``data:`` URI into a reportlab image, or ``None``.

    A malformed or oversized logo is skipped with a warning rather than
    failing the report: branding is cosmetic, and no logo is far better
    than no report.
    """
    try:
        header, _, encoded = data_uri.partition(",")
        if "base64" not in header or not encoded:
            return None
        raw = b64decode(encoded, validate=True)
        if len(raw) > _MAX_LOGO_BYTES:
            logger.warning("Report logo exceeds the size limit; skipping.")
            return None
        image = Image(ImageReader(io.BytesIO(raw)))
        image.drawHeight = 14 * mm
        image.drawWidth = 14 * mm * (image.imageWidth / max(image.imageHeight, 1))
        return image
    except Exception as exc:
        logger.warning("Could not decode report logo.", extra={"extra_fields": {"error": str(exc)}})
        return None


def _chart_drawing(section: RenderedSection, header_color: str) -> Table | None:
    """Render chart points as a proportional bar table.

    Deliberately drawn with table cells rather than
    ``reportlab.graphics``: bars built from coloured cells scale
    correctly on any page size and need no separate drawing canvas,
    and a pie chart's slices are far less readable in print than
    labelled magnitudes anyway.
    """
    if not section.chart_points:
        return None
    largest = max(value for _label, value in section.chart_points)
    rows: list[list[Any]] = []
    for label, value in section.chart_points:
        share = 0.0 if largest <= 0 else value / largest
        filled = round(share * 30)
        bar = "█" * filled if filled else "▖"
        rows.append([label, bar, _format_number(value)])

    table = Table(rows, colWidths=[70 * mm, 75 * mm, 25 * mm])
    table.setStyle(
        TableStyle(
            [
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor(header_color)),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:,.2f}"


def _fit_columns(section: RenderedSection, available_width: float) -> list[float]:
    """Distribute width across columns by their widest content.

    Equal-width columns waste space on a ``status`` column and truncate
    a ``description``; measuring the real strings produces a table that
    is readable without manual tuning per template.
    """
    cells = section.cell_values()
    natural: list[float] = []
    for index, column in enumerate(section.columns):
        widest = stringWidth(column.label, "Helvetica-Bold", 8)
        for row in cells[:200]:  # sampling is enough to size a column
            widest = max(widest, stringWidth(row[index], "Helvetica", 8))
        natural.append(min(widest + 10, available_width * 0.45))

    total = sum(natural) or 1.0
    if total <= available_width:
        slack = (available_width - total) / len(natural)
        return [width + slack for width in natural]
    return [width / total * available_width for width in natural]


def to_pdf(
    report: RenderedReport,
    *,
    signed_by: str | None = None,
    password: str | None = None,
) -> bytes:
    """Render *report* to PDF bytes.

    Args:
        report: The resolved report.
        signed_by: If given, appends a visible signature block. See this
            module's docstring for what that does and does not mean.
        password: If given, encrypts the document. Both the user and
            owner password are set, so the file cannot be opened or
            re-permissioned without it.
    """
    header_color, stripe_color = theme_colors(report.branding.theme)
    buffer = io.BytesIO()

    encryption = None
    if password:
        encryption = pdfencrypt.StandardEncryption(
            userPassword=password, ownerPassword=password, canPrint=1, strength=128
        )

    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        title=report.title,
        author=report.branding.company_name,
        subject=report.subtitle or "",
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        encrypt=encryption,
    )

    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=8, leading=10)
    muted = ParagraphStyle("muted", parent=styles["BodyText"], fontSize=8, textColor=colors.grey)

    story: list[Any] = []
    logo = _logo_flowable(report.branding.logo_data_uri) if report.branding.logo_data_uri else None
    if logo is not None:
        story.append(logo)
    story.append(Paragraph(report.title, styles["Title"]))
    if report.subtitle:
        story.append(Paragraph(report.subtitle, styles["Heading3"]))
    story.append(
        Paragraph(
            f"Generated {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')} "
            f"by {report.branding.company_name}",
            muted,
        )
    )
    story.append(Spacer(1, 8))

    if report.branding.show_table_of_contents:
        story.extend(_table_of_contents(report, styles))

    available_width = landscape(A4)[0] - 30 * mm

    for section in report.sections:
        story.extend(
            _section_flowables(
                section,
                styles=styles,
                muted=muted,
                cell_style=cell_style,
                header_color=header_color,
                stripe_color=stripe_color,
                available_width=available_width,
            )
        )

    if signed_by:
        story.append(Spacer(1, 14))
        story.append(
            Paragraph(
                f"<b>Signed by:</b> {signed_by}<br/>"
                f"<b>Signed at:</b> {datetime.now(UTC).isoformat()}<br/>"
                f"<b>Content SHA-256:</b> {_signature_digest(report)}<br/>"
                "<i>Content digest for tamper detection; not a PKI signature.</i>",
                muted,
            )
        )

    footer = report.branding.footer_text or report.branding.company_name

    def _make_canvas(*args: Any, **kwargs: Any) -> _NumberedCanvas:
        return _NumberedCanvas(*args, footer_text=footer, **kwargs)

    if report.branding.show_page_numbers:
        document.build(story, canvasmaker=_make_canvas)
    else:
        document.build(story)
    return buffer.getvalue()


def _section_flowables(
    section: RenderedSection,
    *,
    styles: Any,
    muted: ParagraphStyle,
    cell_style: ParagraphStyle,
    header_color: str,
    stripe_color: str,
    available_width: float,
) -> list[Any]:
    """Build every flowable for one section.

    Split out of :func:`to_pdf` so that function stays a readable
    assembly of document-level concerns rather than a single body
    branching over every section kind.
    """
    if section.kind is SectionKind.PAGE_BREAK:
        return [PageBreak()]

    flowables: list[Any] = []
    if section.title:
        flowables.append(Paragraph(section.title, styles["Heading2"]))
    if section.error:
        flowables.append(Paragraph(f"<b>Section unavailable:</b> {section.error}", muted))
        flowables.append(Spacer(1, 8))
        return flowables
    if section.text:
        flowables.append(Paragraph(section.text.replace(_NEWLINE, "<br/>"), styles["BodyText"]))
        flowables.append(Spacer(1, 6))
    if section.metric_value is not None:
        flowables.append(
            Paragraph(
                f"<font size=20><b>{_format_number(section.metric_value)}</b></font>"
                f"<br/>{section.metric_label or section.key}",
                styles["BodyText"],
            )
        )
        flowables.append(Spacer(1, 8))
    if section.chart_points and section.chart_kind is not None:
        chart = _chart_drawing(section, header_color)
        if chart is not None:
            flowables.append(chart)
            flowables.append(Spacer(1, 8))
    if section.rows and section.columns:
        flowables.extend(
            _table_flowables(
                section, available_width, header_color, stripe_color, cell_style, muted
            )
        )
    return flowables


def _table_of_contents(report: RenderedReport, styles: Any) -> list[Any]:
    """A simple listing of section titles ("Table of Contents").

    Deliberately not page-linked: ``reportlab``'s linked TOC requires a
    two-pass ``BaseDocTemplate`` with named destinations, and a plain
    contents listing delivers the navigational value for a report of
    this size without that machinery.
    """
    titled = [section for section in report.sections if section.title]
    if len(titled) < 2:  # noqa: PLR2004 -- a one-item contents list is noise
        return []
    entries: list[Any] = [Paragraph("Contents", styles["Heading2"])]
    entries.extend(
        Paragraph(f"{index}. {section.title}", styles["BodyText"])
        for index, section in enumerate(titled, start=1)
    )
    entries.append(Spacer(1, 10))
    return entries


def _table_flowables(
    section: RenderedSection,
    available_width: float,
    header_color: str,
    stripe_color: str,
    cell_style: ParagraphStyle,
    muted: ParagraphStyle,
) -> list[Any]:
    """Build one section's table, truncating visibly if enormous."""
    cells = section.cell_values()
    truncated = len(cells) > _MAX_TABLE_ROWS
    if truncated:
        cells = cells[:_MAX_TABLE_ROWS]

    header = [Paragraph(f"<b>{column.label}</b>", cell_style) for column in section.columns]
    body = [[Paragraph(cell, cell_style) for cell in row] for row in cells]

    table = Table(
        [header, *body],
        colWidths=_fit_columns(section, available_width),
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(stripe_color)]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    flowables: list[Any] = [table]
    if truncated:
        omitted = len(section.rows) - _MAX_TABLE_ROWS
        flowables.append(
            Paragraph(
                f"{omitted:,} further row(s) omitted from this PDF. "
                "Export as CSV or XLSX for the complete data set.",
                muted,
            )
        )
    flowables.append(Spacer(1, 12))
    return flowables


__all__ = ["to_pdf"]
