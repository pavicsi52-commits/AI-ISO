"""Export dispatch -- one entry point for all seven formats.

Everything a caller needs about a format lives in :data:`FORMAT_SPECS`:
the MIME type, the file extension, and the function that produces the
bytes. Callers therefore never branch on format themselves, which is
what stops a new format from having to be added in five places.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass

from shared_core.exceptions.validation import ValidationError

from app.export.excel import to_xlsx
from app.export.pdf import to_pdf
from app.export.text_formats import to_csv, to_html, to_json, to_markdown, to_xml
from app.models.enums import ExportFormat
from app.renderer.document import RenderedReport

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_STEM = 120


@dataclass(frozen=True, slots=True)
class FormatSpec:
    """Everything that varies between export formats."""

    content_type: str
    extension: str
    render: Callable[[RenderedReport], bytes]


FORMAT_SPECS: dict[ExportFormat, FormatSpec] = {
    ExportFormat.PDF: FormatSpec("application/pdf", "pdf", to_pdf),
    ExportFormat.XLSX: FormatSpec(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx", to_xlsx
    ),
    ExportFormat.CSV: FormatSpec("text/csv; charset=utf-8", "csv", to_csv),
    ExportFormat.JSON: FormatSpec("application/json", "json", to_json),
    ExportFormat.MARKDOWN: FormatSpec("text/markdown; charset=utf-8", "md", to_markdown),
    ExportFormat.HTML: FormatSpec("text/html; charset=utf-8", "html", to_html),
    ExportFormat.XML: FormatSpec("application/xml", "xml", to_xml),
}


@dataclass(frozen=True, slots=True)
class ExportedArtifact:
    """One rendered file, ready to persist or deliver."""

    export_format: ExportFormat
    filename: str
    content_type: str
    content: bytes

    @property
    def size_bytes(self) -> int:
        """Length of the rendered content."""
        return len(self.content)

    @property
    def checksum_sha256(self) -> str:
        """SHA-256 of the content.

        Stored alongside the bytes so an archived artifact can be
        verified as unaltered without re-rendering it -- which would
        produce different bytes anyway, since every render stamps a new
        generation timestamp.
        """
        return hashlib.sha256(self.content).hexdigest()


def safe_filename(title: str, export_format: ExportFormat) -> str:
    """Build a filesystem- and header-safe filename for *title*.

    Report titles are user-authored and routinely contain slashes,
    quotes, and newlines. Those go into a ``Content-Disposition``
    header, where an unescaped newline is a header-injection vector --
    so the stem is reduced to a conservative character set rather than
    merely trimmed.
    """
    spec = FORMAT_SPECS[export_format]
    stem = _UNSAFE_FILENAME.sub("-", title).strip("-._") or "report"
    return f"{stem[:_MAX_STEM]}.{spec.extension}"


def export(report: RenderedReport, export_format: ExportFormat) -> ExportedArtifact:
    """Render *report* in *export_format*.

    Raises:
        ValidationError: If the format is not supported.
    """
    spec = FORMAT_SPECS.get(export_format)
    if spec is None:
        supported = ", ".join(sorted(str(member) for member in FORMAT_SPECS))
        raise ValidationError(
            f"Export format {export_format!r} is not supported. Supported: {supported}."
        )
    return ExportedArtifact(
        export_format=export_format,
        filename=safe_filename(report.title, export_format),
        content_type=spec.content_type,
        content=spec.render(report),
    )


def export_pdf_protected(
    report: RenderedReport, *, signed_by: str | None = None, password: str | None = None
) -> ExportedArtifact:
    """Render a PDF with an optional signature block and/or password.

    Separate from :func:`export` because these options are PDF-only;
    folding them into the generic signature would put parameters on
    every format that cannot honour them.
    """
    spec = FORMAT_SPECS[ExportFormat.PDF]
    return ExportedArtifact(
        export_format=ExportFormat.PDF,
        filename=safe_filename(report.title, ExportFormat.PDF),
        content_type=spec.content_type,
        content=to_pdf(report, signed_by=signed_by, password=password),
    )


__all__ = [
    "FORMAT_SPECS",
    "ExportedArtifact",
    "FormatSpec",
    "export",
    "export_pdf_protected",
    "safe_filename",
]
