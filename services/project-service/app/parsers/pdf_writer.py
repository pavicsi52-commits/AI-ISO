"""PDF export writing, via ``reportlab``.

Per docs/034 "EXPORT": "PDF Summary" -- a summary report, not a flat
per-row table the way ``services/user-management-service``'s own PDF
export is (that service's own docstring notes "PDF" there is just
another flat target format alongside CSV/Excel/JSON). A project export
summary instead composes a short narrative header (export scope,
generation time, project count) followed by the same styled table
shape, using ``reportlab.platypus``' richer flow-document primitives
(``Paragraph``/``Spacer``) rather than only ``Table``.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def write_pdf_summary(rows: list[dict[str, Any]], fieldnames: list[str]) -> bytes:
    """Serialize *rows* to a summary PDF: a narrative header plus a styled table."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    styles = getSampleStyleSheet()

    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    story = [
        Paragraph("AI-IOS Project Export Summary", styles["Title"]),
        Paragraph(f"Generated {generated_at} &mdash; {len(rows)} project(s).", styles["Normal"]),
        Spacer(1, 16),
    ]

    table_data = [fieldnames] + [[str(row.get(field, "")) for field in fieldnames] for row in rows]
    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
            ]
        )
    )
    story.append(table)
    document.build(story)
    return buffer.getvalue()


__all__ = ["write_pdf_summary"]
