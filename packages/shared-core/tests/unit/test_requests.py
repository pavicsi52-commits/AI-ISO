"""Tests for reusable inbound request DTOs."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from shared_core.requests import (
    BulkRequest,
    DataFormat,
    ExportRequest,
    FilterRequest,
    ImportRequest,
    PaginationRequest,
    SearchRequest,
    SortRequest,
)
from shared_core.schemas import FilterOperator, FilterParams, SortParams


def test_pagination_request_inherits_pagination_params() -> None:
    request = PaginationRequest(page=2, page_size=50)

    assert request.page == 2
    assert request.offset == 50


def test_search_request_accepts_query() -> None:
    request = SearchRequest(q="postgres")

    assert request.q == "postgres"


def test_search_request_defaults_to_none() -> None:
    assert SearchRequest().q is None


def test_filter_request_holds_multiple_clauses() -> None:
    request = FilterRequest(
        filters=[FilterParams(field="status", operator=FilterOperator.EQUALS, value="active")]
    )

    assert len(request.filters) == 1


def test_sort_request_holds_multiple_keys() -> None:
    request = SortRequest(sort=[SortParams(field="name"), SortParams(field="created_at")])

    assert len(request.sort) == 2


def test_bulk_request_requires_at_least_one_id() -> None:
    with pytest.raises(PydanticValidationError):
        BulkRequest(ids=[])


def test_bulk_request_rejects_duplicate_ids() -> None:
    shared_id = uuid4()
    with pytest.raises(PydanticValidationError):
        BulkRequest(ids=[shared_id, shared_id])


def test_bulk_request_accepts_unique_ids() -> None:
    request = BulkRequest(ids=[uuid4(), uuid4()])

    assert len(request.ids) == 2


def test_import_request_defaults_to_json_and_not_dry_run() -> None:
    request = ImportRequest(storage_key="uploads/x.json")

    assert request.format == DataFormat.JSON
    assert request.dry_run is False


def test_export_request_defaults_to_empty_filters() -> None:
    request = ExportRequest()

    assert request.filters == []
    assert request.format == DataFormat.JSON
