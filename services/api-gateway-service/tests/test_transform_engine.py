"""Pure tests for app/transform/engine.py -- no database, no fixtures."""

from __future__ import annotations

import pytest

from app.transform.engine import (
    apply_body_transform,
    apply_header_transform,
    apply_url_rewrite,
    inject_metadata_headers,
    normalize_error_body,
)

pytestmark = pytest.mark.asyncio


class TestApplyHeaderTransform:
    async def test_empty_config_returns_an_equal_but_distinct_copy(self) -> None:
        headers = {"X-Foo": "1"}
        result = apply_header_transform(headers, {})
        assert result == headers
        assert result is not headers

    async def test_add_inserts_new_headers(self) -> None:
        result = apply_header_transform({}, {"add": {"X-New": "value"}})
        assert result == {"X-New": "value"}

    async def test_remove_is_case_insensitive(self) -> None:
        result = apply_header_transform({"X-Foo": "1"}, {"remove": ["x-foo"]})
        assert result == {}

    async def test_remove_of_an_absent_header_is_a_no_op(self) -> None:
        result = apply_header_transform({"X-Foo": "1"}, {"remove": ["x-bar"]})
        assert result == {"X-Foo": "1"}

    async def test_add_wins_over_remove_for_the_same_header(self) -> None:
        result = apply_header_transform(
            {"X-Foo": "old"}, {"remove": ["X-Foo"], "add": {"X-Foo": "new"}}
        )
        assert result == {"X-Foo": "new"}

    async def test_add_does_not_case_normalize_against_an_existing_header(self) -> None:
        # `remove` lowercases for comparison; `add` writes the config key verbatim -- an `add`
        # key differing only in case from an existing header creates a second, distinct entry.
        result = apply_header_transform({"X-Foo": "1"}, {"add": {"x-foo": "2"}})
        assert result == {"X-Foo": "1", "x-foo": "2"}

    async def test_add_values_are_coerced_to_strings(self) -> None:
        result = apply_header_transform({}, {"add": {"X-Count": 5}})
        assert result == {"X-Count": "5"}


class TestApplyUrlRewrite:
    async def test_rewrites_the_path_via_pattern_and_replacement(self) -> None:
        result = apply_url_rewrite(
            "/old/123", {"pattern": r"^/old/(.*)$", "replacement": r"/new/\1"}
        )
        assert result == "/new/123"

    async def test_missing_pattern_leaves_the_path_unchanged(self) -> None:
        assert apply_url_rewrite("/orders", {"replacement": "/x"}) == "/orders"

    async def test_empty_pattern_leaves_the_path_unchanged(self) -> None:
        assert apply_url_rewrite("/orders", {"pattern": "", "replacement": "/x"}) == "/orders"

    async def test_missing_replacement_leaves_the_path_unchanged(self) -> None:
        assert apply_url_rewrite("/orders", {"pattern": r"^/orders$"}) == "/orders"

    async def test_an_empty_string_replacement_is_honored_since_it_is_not_none(self) -> None:
        result = apply_url_rewrite("/orders", {"pattern": r"^/orders$", "replacement": ""})
        assert result == ""

    async def test_no_config_at_all_leaves_the_path_unchanged(self) -> None:
        assert apply_url_rewrite("/orders", {}) == "/orders"


class TestInjectMetadataHeaders:
    async def test_injects_both_correlation_and_request_id_headers(self) -> None:
        result = inject_metadata_headers({}, correlation_id="corr-1", request_id="req-1")
        assert result == {"X-Correlation-ID": "corr-1", "X-Request-ID": "req-1"}

    async def test_never_overwrites_an_existing_correlation_id(self) -> None:
        result = inject_metadata_headers(
            {"X-Correlation-ID": "existing"}, correlation_id="corr-1", request_id="req-1"
        )
        assert result["X-Correlation-ID"] == "existing"

    async def test_never_overwrites_an_existing_request_id(self) -> None:
        result = inject_metadata_headers(
            {"X-Request-ID": "existing"}, correlation_id="corr-1", request_id="req-1"
        )
        assert result["X-Request-ID"] == "existing"

    async def test_returns_a_distinct_copy_of_the_input(self) -> None:
        headers = {"X-Other": "1"}
        result = inject_metadata_headers(headers, correlation_id="c", request_id="r")
        assert result is not headers
        assert "X-Correlation-ID" not in headers


class TestNormalizeErrorBody:
    async def test_builds_the_uniform_error_shape(self) -> None:
        body = normalize_error_body(status_code=503, detail="upstream down", request_id="req-1")
        assert body == {
            "success": False,
            "error": {"status_code": 503, "message": "upstream down"},
            "request_id": "req-1",
        }


class TestApplyBodyTransform:
    async def test_empty_config_returns_an_equal_but_distinct_copy(self) -> None:
        body = {"a": 1}
        result = apply_body_transform(body, {})
        assert result == body
        assert result is not body

    async def test_removes_a_top_level_field(self) -> None:
        result = apply_body_transform({"a": 1, "b": 2}, {"remove": ["a"]})
        assert result == {"b": 2}

    async def test_remove_of_an_absent_field_is_a_no_op(self) -> None:
        result = apply_body_transform({"a": 1}, {"remove": ["missing"]})
        assert result == {"a": 1}

    async def test_renames_an_existing_field(self) -> None:
        result = apply_body_transform({"old": 1}, {"rename": {"old": "new"}})
        assert result == {"new": 1}

    async def test_rename_of_a_missing_field_is_a_no_op(self) -> None:
        result = apply_body_transform({"a": 1}, {"rename": {"missing": "new"}})
        assert result == {"a": 1}

    async def test_add_inserts_a_new_field(self) -> None:
        result = apply_body_transform({}, {"add": {"c": 3}})
        assert result == {"c": 3}

    async def test_add_overrides_an_existing_field(self) -> None:
        result = apply_body_transform({"a": 1}, {"add": {"a": 2}})
        assert result == {"a": 2}

    async def test_remove_then_rename_then_add_apply_in_that_order(self) -> None:
        # "a" is removed first, so renaming it is then a no-op; "add" can still re-introduce it.
        result = apply_body_transform(
            {"a": 1, "b": 2},
            {"remove": ["a"], "rename": {"a": "a2", "b": "b2"}, "add": {"a": 99}},
        )
        assert result == {"b2": 2, "a": 99}
