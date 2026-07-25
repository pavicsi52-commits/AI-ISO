"""Tests for shared schema building blocks."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError
from shared_core.schemas import (
    FilterOperator,
    FilterParams,
    PaginationMeta,
    PaginationParams,
    ResponseMeta,
    SortOrder,
    SortParams,
)


def test_pagination_params_defaults() -> None:
    params = PaginationParams()

    assert params.page == 1
    assert params.page_size == 25
    assert params.offset == 0


def test_pagination_params_offset_computation() -> None:
    params = PaginationParams(page=3, page_size=10)

    assert params.offset == 20


def test_pagination_params_rejects_page_size_over_max() -> None:
    with pytest.raises(PydanticValidationError):
        PaginationParams(page_size=101)


def test_pagination_params_rejects_zero_page() -> None:
    with pytest.raises(PydanticValidationError):
        PaginationParams(page=0)


def test_pagination_meta_from_params_computes_has_next() -> None:
    meta = PaginationMeta.from_params(PaginationParams(page=1, page_size=10), total=25)

    assert meta.has_next is True
    assert meta.has_previous is False


def test_pagination_meta_from_params_last_page_has_no_next() -> None:
    meta = PaginationMeta.from_params(PaginationParams(page=3, page_size=10), total=25)

    assert meta.has_next is False
    assert meta.has_previous is True


def test_pagination_meta_rejects_inconsistent_has_previous() -> None:
    with pytest.raises(PydanticValidationError):
        PaginationMeta(page=1, page_size=10, total=5, has_next=False, has_previous=True)


def test_sort_params_defaults_to_ascending() -> None:
    params = SortParams(field="name")

    assert params.order == SortOrder.ASC


def test_filter_params_holds_operator_and_value() -> None:
    params = FilterParams(field="status", operator=FilterOperator.EQUALS, value="healthy")

    assert params.operator == FilterOperator.EQUALS
    assert params.value == "healthy"


def test_response_meta_defaults_timestamp() -> None:
    meta = ResponseMeta(request_id="req-1")

    assert meta.request_id == "req-1"
    assert meta.timestamp is not None


def test_base_schema_rejects_unknown_fields() -> None:
    with pytest.raises(PydanticValidationError):
        PaginationParams(page=1, unknown_field="x")
