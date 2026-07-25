"""PDF export writing, via ``reportlab``.

No ``shared_core`` equivalent exists (confirmed by this package's own
reuse research: no PDF library is a dependency anywhere else in this
monorepo). A single simple table -- one row per user, one column per
field -- is all docs/031 "EXPORT" asks for ("PDF" is listed as a
target format alongside CSV/Excel/JSON, with no further requirement).
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle


def write_pdf_rows(rows: list[dict[str, Any]], fieldnames: list[str]) -> bytes:
    """Serialize *rows* to a simple tabular PDF, with *fieldnames* as the column order."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=landscape(letter))
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
    document.build([table])
    return buffer.getvalue()


__all__ = ["write_pdf_rows"]
