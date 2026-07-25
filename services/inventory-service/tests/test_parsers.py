"""Round-trip tests for every import/export parser."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from shared_core.exceptions.validation import ValidationError

from app.parsers.csv_parser import parse_csv_rows, write_csv_rows
from app.parsers.excel_parser import parse_excel_rows, write_excel_rows
from app.parsers.json_parser import parse_json_rows, write_json_rows
from app.parsers.pdf_writer import write_pdf_summary
from app.parsers.yaml_parser import parse_yaml_rows, write_yaml_rows
from app.parsers.zip_archive import build_export_package, extract_single_data_file

_FIELDNAMES = ["name", "hostname", "asset_type"]
_ROWS = [
    {"name": "web-01", "hostname": "web-01.internal", "asset_type": "virtual_machine"},
    {"name": "db-01", "hostname": "db-01.internal", "asset_type": "database"},
]


def test_json_round_trip() -> None:
    payload = write_json_rows(_ROWS)
    assert parse_json_rows(payload) == _ROWS


def test_json_parse_rejects_non_list() -> None:
    with pytest.raises(ValidationError):
        parse_json_rows(json.dumps({"not": "a list"}).encode())


def test_json_parse_rejects_invalid_json() -> None:
    with pytest.raises(ValidationError):
        parse_json_rows(b"{not valid json")


def test_yaml_round_trip() -> None:
    payload = write_yaml_rows(_ROWS)
    assert parse_yaml_rows(payload) == _ROWS


def test_yaml_parse_rejects_invalid_yaml() -> None:
    with pytest.raises(ValidationError):
        parse_yaml_rows(b"not: valid: yaml: [")


def test_csv_round_trip() -> None:
    payload = write_csv_rows(_ROWS, _FIELDNAMES)
    parsed = list(parse_csv_rows(payload))
    assert parsed == _ROWS


def test_excel_round_trip() -> None:
    payload = write_excel_rows(_ROWS, _FIELDNAMES)
    parsed = list(parse_excel_rows(payload))
    assert parsed == _ROWS


def test_pdf_summary_is_nonempty_pdf() -> None:
    payload = write_pdf_summary(_ROWS, _FIELDNAMES)
    assert payload.startswith(b"%PDF")


def test_zip_export_bundle_rejected_as_import() -> None:
    package = build_export_package(
        json_bytes=write_json_rows(_ROWS),
        yaml_bytes=write_yaml_rows(_ROWS),
        csv_bytes=write_csv_rows(_ROWS, _FIELDNAMES),
        excel_bytes=write_excel_rows(_ROWS, _FIELDNAMES),
        pdf_bytes=write_pdf_summary(_ROWS, _FIELDNAMES),
        row_count=len(_ROWS),
    )
    with pytest.raises(ValidationError):
        extract_single_data_file(package)


def test_zip_single_file_import_accepted() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr("assets.json", write_json_rows(_ROWS))
    filename, content = extract_single_data_file(buffer.getvalue())
    assert filename == "assets.json"
    assert parse_json_rows(content) == _ROWS


def test_zip_invalid_archive_rejected() -> None:
    with pytest.raises(ValidationError):
        extract_single_data_file(b"not a zip file")


__all__: list[str] = []
