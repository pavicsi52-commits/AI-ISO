"""Tests for :mod:`app.parsers` -- CSV/Excel/JSON/PDF import and export."""

from __future__ import annotations

import pytest
from shared_core.exceptions.validation import ValidationError

from app.parsers.csv_parser import parse_csv_rows, write_csv_rows
from app.parsers.excel_parser import parse_excel_rows, write_excel_rows
from app.parsers.json_parser import parse_json_rows, write_json_rows
from app.parsers.pdf_writer import write_pdf_rows

_ROWS = [
    {"username": "a", "email": "a@example.com"},
    {"username": "b", "email": "b@example.com"},
]
_FIELDS = ["username", "email"]


def test_csv_round_trip() -> None:
    content = write_csv_rows(_ROWS, _FIELDS)

    parsed = parse_csv_rows(content)

    assert parsed == _ROWS


def test_csv_parse_empty_file_returns_empty_list() -> None:
    assert parse_csv_rows(b"") == []


def test_excel_round_trip() -> None:
    content = write_excel_rows(_ROWS, _FIELDS)

    parsed = parse_excel_rows(content)

    assert parsed == _ROWS


def test_excel_parse_ignores_blank_rows() -> None:
    content = write_excel_rows(_ROWS, _FIELDS)

    parsed = parse_excel_rows(content)

    assert all(any(v for v in row.values()) for row in parsed)


def test_json_round_trip() -> None:
    content = write_json_rows(_ROWS)

    parsed = parse_json_rows(content)

    assert parsed == _ROWS


def test_json_parse_rejects_malformed_json() -> None:
    with pytest.raises(ValidationError):
        parse_json_rows(b"{not valid json")


def test_json_parse_rejects_non_array() -> None:
    with pytest.raises(ValidationError):
        parse_json_rows(b'{"not": "an array"}')


def test_json_parse_rejects_array_of_non_objects() -> None:
    with pytest.raises(ValidationError):
        parse_json_rows(b"[1, 2, 3]")


def test_pdf_writer_produces_a_pdf() -> None:
    content = write_pdf_rows(_ROWS, _FIELDS)

    assert content.startswith(b"%PDF")
    assert len(content) > 0


def test_pdf_writer_handles_empty_rows() -> None:
    content = write_pdf_rows([], _FIELDS)

    assert content.startswith(b"%PDF")
