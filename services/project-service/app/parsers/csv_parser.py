"""CSV import/export parsing.

Python's stdlib ``csv`` module is sufficient (no ``shared_core``
wrapper exists for this, matching
``services/user-management-service``'s own identical precedent).
"""

from __future__ import annotations

import csv
import io
from typing import Any


def parse_csv_rows(content: bytes) -> list[dict[str, str]]:
    """Parse *content* (a CSV file's raw bytes) into a list of header-keyed row dicts."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def write_csv_rows(rows: list[dict[str, Any]], fieldnames: list[str]) -> bytes:
    """Serialize *rows* to CSV bytes, with *fieldnames* as the column order."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


__all__ = ["parse_csv_rows", "write_csv_rows"]
