"""ZIP Package import/export, via the stdlib ``zipfile`` module.

Per docs/036 "IMPORT"/"EXPORT": "ZIP". Extends
``services/project-service``'s own ``zip_archive.py`` precedent (JSON/
YAML/CSV only) with the two additional formats docs/036 lists that
docs/034 never needed: Excel (import and export) and PDF
(export-only summary, never a re-importable format).

A ZIP *import* package is expected to contain exactly one data file
(``.json``, ``.yaml``/``.yml``, ``.csv``, or ``.xlsx``) at its root --
this service doesn't support multi-file archives, since an inventory
import is a single logical dataset. A ZIP *export* package bundles the
same export data in all four re-importable formats plus a PDF summary
and a ``manifest.json`` describing the export, for a recipient who
doesn't know in advance which format they'll want to consume.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Any

from shared_core.exceptions.validation import ValidationError

_DATA_EXTENSIONS = (".json", ".yaml", ".yml", ".csv", ".xlsx")


def extract_single_data_file(content: bytes) -> tuple[str, bytes]:
    """Extract the one data file from a ZIP import package.

    Returns:
        A ``(filename, content)`` pair for the single recognized data
        file found at the archive's root.

    Raises:
        ValidationError: If *content* isn't a valid ZIP, or doesn't
            contain exactly one recognized data file.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if not name.endswith("/") and name.lower().endswith(_DATA_EXTENSIONS)
            ]
            if len(candidates) != 1:
                raise ValidationError(
                    "ZIP import package must contain exactly one "
                    ".json/.yaml/.csv/.xlsx data file at its root "
                    f"(found {len(candidates)})."
                )
            return candidates[0], archive.read(candidates[0])
    except zipfile.BadZipFile as exc:
        raise ValidationError(f"Invalid ZIP archive: {exc}") from exc


def build_export_package(
    *,
    json_bytes: bytes,
    yaml_bytes: bytes,
    csv_bytes: bytes,
    excel_bytes: bytes,
    pdf_bytes: bytes,
    row_count: int,
) -> bytes:
    """Bundle an export's JSON/YAML/CSV/Excel/PDF representations plus a
    manifest into one ZIP Package.
    """
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "row_count": row_count,
        "files": ["export.json", "export.yaml", "export.csv", "export.xlsx", "export.pdf"],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("export.json", json_bytes)
        archive.writestr("export.yaml", yaml_bytes)
        archive.writestr("export.csv", csv_bytes)
        archive.writestr("export.xlsx", excel_bytes)
        archive.writestr("export.pdf", pdf_bytes)
    return buffer.getvalue()


__all__ = ["build_export_package", "extract_single_data_file"]
