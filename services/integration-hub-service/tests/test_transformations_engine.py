"""Pure tests for app/transformations/engine.py -- no database, no fixtures.

Every function under test is ordinary, dependency-free Python (stdlib
csv/json/xml.etree.ElementTree plus PyYAML) -- nothing here mocks I/O,
because there is none to mock. `_resolve_path`/`_set_path`/`_delete_path`
are tested directly, the same "private helper worth its own coverage"
precedent webhook-service's own sibling suite already sets for its
equivalent dotted-path helpers.
"""

from __future__ import annotations

import json
from typing import ClassVar

import pytest
import yaml

from app.models.enums import DataFormat, TransformationKind
from app.transformations.engine import (
    _delete_path,
    _resolve_path,
    _set_path,
    apply_aggregation,
    apply_enrichment,
    apply_field_mapping,
    apply_filtering,
    apply_normalization,
    apply_transformation,
    evaluate_rule,
    parse_document,
    render_document,
    validate_schema,
)


def _rule(field: str, operator: str, value: object = None) -> dict:
    return {"field": field, "operator": operator, "value": value}


class TestResolvePath:
    def test_top_level_key(self) -> None:
        assert _resolve_path({"a": 1}, "a") == 1

    def test_nested_key_two_levels(self) -> None:
        assert _resolve_path({"a": {"b": 2}}, "a.b") == 2

    def test_nested_key_three_levels(self) -> None:
        assert _resolve_path({"a": {"b": {"c": "deep"}}}, "a.b.c") == "deep"

    def test_missing_top_level_key_resolves_to_none(self) -> None:
        assert _resolve_path({"a": 1}, "missing") is None

    def test_missing_intermediate_key_resolves_to_none(self) -> None:
        assert _resolve_path({"a": {}}, "a.b") is None

    def test_non_mapping_intermediate_value_resolves_to_none(self) -> None:
        # "a" resolves to the int 1, which cannot be descended into via ".b".
        assert _resolve_path({"a": 1}, "a.b") is None


class TestSetPath:
    def test_sets_a_top_level_key(self) -> None:
        payload: dict = {}
        _set_path(payload, "a", 1)
        assert payload == {"a": 1}

    def test_creates_intermediate_dicts_for_a_nested_path(self) -> None:
        payload: dict = {}
        _set_path(payload, "a.b.c", "deep")
        assert payload == {"a": {"b": {"c": "deep"}}}

    def test_overwrites_an_existing_nested_value(self) -> None:
        payload = {"a": {"b": "old"}}
        _set_path(payload, "a.b", "new")
        assert payload == {"a": {"b": "new"}}

    def test_setting_a_nested_key_does_not_mutate_a_shared_nested_dict_object(self) -> None:
        # Regression test for a fixed bug: `_set_path` used to descend into an already
        # existing nested dict by reference instead of copying it first, so setting a
        # nested path that already existed silently mutated whatever *other* object
        # happened to share that nested dict -- exactly the situation every caller here
        # (`apply_field_mapping`/`apply_enrichment`/`apply_normalization`) creates via its
        # own top-level `dict(data)` shallow copy, which shares every nested dict object
        # with the caller's original, un-copied input.
        shared_nested = {"b": "old"}
        outer = {"a": shared_nested}
        _set_path(outer, "a.b", "new")
        assert outer == {"a": {"b": "new"}}
        assert shared_nested == {"b": "old"}
        assert outer["a"] is not shared_nested


class TestDeletePath:
    def test_deletes_a_top_level_key(self) -> None:
        payload = {"a": 1, "b": 2}
        _delete_path(payload, "a")
        assert payload == {"b": 2}

    def test_deletes_a_nested_key(self) -> None:
        payload = {"a": {"b": 1, "c": 2}}
        _delete_path(payload, "a.b")
        assert payload == {"a": {"c": 2}}

    def test_missing_intermediate_key_is_a_silent_no_op(self) -> None:
        payload = {"a": {}}
        _delete_path(payload, "a.b.c")
        assert payload == {"a": {}}

    def test_non_mapping_intermediate_value_is_a_silent_no_op(self) -> None:
        payload = {"a": 5}
        _delete_path(payload, "a.b.c")
        assert payload == {"a": 5}

    def test_a_non_dict_final_parent_is_a_silent_no_op(self) -> None:
        # Two-level path where the parent resolves to a non-dict scalar.
        payload = {"a": 5}
        _delete_path(payload, "a.b")
        assert payload == {"a": 5}

    def test_deleting_a_missing_leaf_key_does_not_raise(self) -> None:
        payload = {"a": {}}
        _delete_path(payload, "a.missing")
        assert payload == {"a": {}}

    def test_deleting_a_nested_key_does_not_mutate_a_shared_nested_dict_object(self) -> None:
        # Same fixed-bug regression as `_set_path`'s own equivalent test above, for the
        # delete side -- see that test's docstring for the full explanation.
        shared_nested = {"b": 1, "c": 2}
        outer = {"a": shared_nested}
        _delete_path(outer, "a.b")
        assert outer == {"a": {"c": 2}}
        assert shared_nested == {"b": 1, "c": 2}
        assert outer["a"] is not shared_nested


class TestParseDocumentJson:
    def test_parses_a_json_object(self) -> None:
        parsed = parse_document('{"a": 1, "b": [1, 2, 3]}', DataFormat.JSON)
        assert parsed == {"a": 1, "b": [1, 2, 3]}

    def test_blank_input_parses_to_an_empty_dict(self) -> None:
        assert parse_document("", DataFormat.JSON) == {}

    def test_whitespace_only_input_parses_to_an_empty_dict(self) -> None:
        assert parse_document("   \n  ", DataFormat.JSON) == {}


class TestParseDocumentYaml:
    def test_parses_a_yaml_mapping(self) -> None:
        raw = "a: 1\nb:\n  - 1\n  - 2\n"
        assert parse_document(raw, DataFormat.YAML) == {"a": 1, "b": [1, 2]}

    def test_blank_input_parses_to_an_empty_dict(self) -> None:
        assert parse_document("", DataFormat.YAML) == {}


class TestParseDocumentCsv:
    def test_parses_rows_into_a_list_of_dicts(self) -> None:
        raw = "name,age\nAda,30\nGrace,85\n"
        assert parse_document(raw, DataFormat.CSV) == [
            {"name": "Ada", "age": "30"},
            {"name": "Grace", "age": "85"},
        ]

    def test_every_value_is_a_string_even_for_a_numeric_looking_column(self) -> None:
        rows = parse_document("count\n5\n", DataFormat.CSV)
        assert rows[0]["count"] == "5"
        assert isinstance(rows[0]["count"], str)

    def test_blank_input_parses_to_an_empty_list(self) -> None:
        assert parse_document("", DataFormat.CSV) == []

    def test_header_only_input_parses_to_an_empty_list(self) -> None:
        assert parse_document("name,age\n", DataFormat.CSV) == []


class TestParseDocumentXml:
    def test_parses_attributes_with_an_at_prefix(self) -> None:
        parsed = parse_document('<person id="1"><name>Ada</name></person>', DataFormat.XML)
        assert parsed == {"person": {"@id": "1", "name": "Ada"}}

    def test_repeated_child_tags_collapse_into_a_list(self) -> None:
        raw = "<tags><tag>x</tag><tag>y</tag></tags>"
        assert parse_document(raw, DataFormat.XML) == {"tags": {"tag": ["x", "y"]}}

    def test_a_third_repeated_child_tag_appends_to_the_existing_list(self) -> None:
        raw = "<tags><tag>x</tag><tag>y</tag><tag>z</tag></tags>"
        assert parse_document(raw, DataFormat.XML) == {"tags": {"tag": ["x", "y", "z"]}}

    def test_a_leaf_with_only_attributes_has_no_text_key(self) -> None:
        assert parse_document('<img src="x.png"/>', DataFormat.XML) == {"img": {"@src": "x.png"}}

    def test_a_leaf_with_no_children_and_no_attributes_is_its_own_text_value(self) -> None:
        assert parse_document("<name>Ada</name>", DataFormat.XML) == {"name": "Ada"}

    def test_an_empty_leaf_element_parses_to_none(self) -> None:
        assert parse_document("<empty></empty>", DataFormat.XML) == {"empty": None}

    def test_mixed_text_and_attributes_on_one_element_keeps_both(self) -> None:
        raw = '<note lang="en">hello</note>'
        assert parse_document(raw, DataFormat.XML) == {"note": {"@lang": "en", "#text": "hello"}}

    def test_an_element_with_both_a_child_and_its_own_direct_text_keeps_both(self) -> None:
        raw = "<order>pending<item>widget</item></order>"
        parsed = parse_document(raw, DataFormat.XML)
        assert parsed == {"order": {"item": "widget", "#text": "pending"}}


class TestRenderDocumentJson:
    def test_renders_valid_json_text(self) -> None:
        rendered = render_document({"a": 1, "b": [1, 2]}, DataFormat.JSON)
        assert json.loads(rendered) == {"a": 1, "b": [1, 2]}


class TestRenderDocumentYaml:
    def test_renders_valid_yaml_text(self) -> None:
        rendered = render_document({"a": 1, "b": [1, 2]}, DataFormat.YAML)
        assert yaml.safe_load(rendered) == {"a": 1, "b": [1, 2]}


class TestRenderDocumentCsv:
    def test_renders_a_header_row_and_one_data_row_per_dict(self) -> None:
        rendered = render_document([{"a": "1", "b": "2"}], DataFormat.CSV)
        assert rendered == "a,b\r\n1,2\r\n"

    def test_wraps_a_single_dict_in_a_one_row_list(self) -> None:
        rendered = render_document({"a": 1, "b": 2}, DataFormat.CSV)
        assert rendered == "a,b\r\n1,2\r\n"

    def test_an_empty_row_list_renders_to_an_empty_string(self) -> None:
        assert render_document([], DataFormat.CSV) == ""

    def test_fieldnames_are_the_union_of_every_row_key_in_first_seen_order(self) -> None:
        rendered = render_document([{"a": 1}, {"b": 2}], DataFormat.CSV)
        assert rendered == "a,b\r\n1,\r\n,2\r\n"


class TestRenderDocumentXml:
    def test_renders_the_single_top_level_key_as_the_root_tag(self) -> None:
        rendered = render_document({"person": {"@id": "1", "name": "Ada"}}, DataFormat.XML)
        assert rendered == '<person id="1"><name>Ada</name></person>'

    def test_a_multi_key_mapping_falls_back_to_the_default_xml_root_tag(self) -> None:
        rendered = render_document({"a": 1, "b": 2}, DataFormat.XML)
        assert rendered == "<root><a>1</a><b>2</b></root>"

    def test_a_multi_key_mapping_uses_a_custom_xml_root_tag_when_given(self) -> None:
        rendered = render_document({"a": 1, "b": 2}, DataFormat.XML, xml_root="custom")
        assert rendered == "<custom><a>1</a><b>2</b></custom>"

    def test_a_non_mapping_value_renders_as_the_root_elements_own_text(self) -> None:
        rendered = render_document([1, 2, 3], DataFormat.XML)
        assert rendered == "<root>[1, 2, 3]</root>"

    def test_a_none_value_renders_as_an_empty_self_closing_element(self) -> None:
        rendered = render_document({"root": {"a": None}}, DataFormat.XML)
        assert rendered == "<root><a /></root>"

    def test_a_list_valued_key_renders_as_repeated_sibling_elements(self) -> None:
        rendered = render_document({"tags": {"tag": ["x", "y"]}}, DataFormat.XML)
        assert rendered == "<tags><tag>x</tag><tag>y</tag></tags>"


class TestRoundTripStability:
    def test_json_parse_then_render_reproduces_equivalent_data(self) -> None:
        data = {"a": 1, "b": [1, 2, 3], "c": {"d": "e"}}
        reparsed = parse_document(render_document(data, DataFormat.JSON), DataFormat.JSON)
        assert reparsed == data

    def test_yaml_parse_then_render_reproduces_equivalent_data(self) -> None:
        data = {"a": 1, "b": [1, 2, 3], "c": {"d": "e"}}
        reparsed = parse_document(render_document(data, DataFormat.YAML), DataFormat.YAML)
        assert reparsed == data

    def test_csv_parse_then_render_reproduces_equivalent_data(self) -> None:
        rows = [{"name": "Ada", "age": "30"}, {"name": "Grace", "age": "85"}]
        reparsed = parse_document(render_document(rows, DataFormat.CSV), DataFormat.CSV)
        assert reparsed == rows

    def test_xml_parse_then_render_reproduces_an_equivalent_string(self) -> None:
        raw = '<person id="1"><name>Ada</name><tags><tag>x</tag><tag>y</tag></tags></person>'
        parsed = parse_document(raw, DataFormat.XML)
        rendered = render_document(parsed, DataFormat.XML)
        assert rendered == raw

    def test_xml_parse_render_parse_is_stable(self) -> None:
        # The stronger guarantee docs/058 actually needs: even if the rendered string isn't
        # byte-identical to some arbitrary input XML, re-parsing what this engine itself
        # rendered must reproduce the exact same canonical value, forever after.
        raw = (
            '<person id="1"><name lang="en">Ada</name>'
            "<tags><tag>x</tag><tag>y</tag></tags></person>"
        )
        first_pass = parse_document(raw, DataFormat.XML)
        second_pass = parse_document(render_document(first_pass, DataFormat.XML), DataFormat.XML)
        third_pass = parse_document(render_document(second_pass, DataFormat.XML), DataFormat.XML)
        assert first_pass == second_pass == third_pass


class TestEvaluateRule:
    def test_eq_matches(self) -> None:
        assert evaluate_rule({"status": "open"}, _rule("status", "eq", "open")) is True

    def test_eq_mismatches(self) -> None:
        assert evaluate_rule({"status": "open"}, _rule("status", "eq", "closed")) is False

    def test_operator_defaults_to_eq_when_omitted(self) -> None:
        rule = {"field": "status", "value": "open"}
        assert evaluate_rule({"status": "open"}, rule) is True

    def test_ne_matches_on_difference(self) -> None:
        assert evaluate_rule({"status": "open"}, _rule("status", "ne", "closed")) is True

    def test_ne_mismatches_on_equality(self) -> None:
        assert evaluate_rule({"status": "open"}, _rule("status", "ne", "open")) is False

    def test_in_matches_when_value_present(self) -> None:
        rule = _rule("status", "in", ["open", "pending"])
        assert evaluate_rule({"status": "open"}, rule) is True

    def test_in_mismatches_when_value_absent(self) -> None:
        rule = _rule("status", "in", ["closed"])
        assert evaluate_rule({"status": "open"}, rule) is False

    def test_in_with_no_expected_value_is_defensively_false(self) -> None:
        rule = {"field": "status", "operator": "in"}
        assert evaluate_rule({"status": "open"}, rule) is False

    def test_not_in_matches_when_value_absent(self) -> None:
        rule = _rule("status", "not_in", ["closed"])
        assert evaluate_rule({"status": "open"}, rule) is True

    def test_not_in_mismatches_when_value_present(self) -> None:
        rule = _rule("status", "not_in", ["open", "pending"])
        assert evaluate_rule({"status": "open"}, rule) is False

    def test_not_in_with_no_expected_value_is_defensively_true(self) -> None:
        rule = {"field": "status", "operator": "not_in"}
        assert evaluate_rule({"status": "open"}, rule) is True

    def test_contains_matches_within_a_string(self) -> None:
        rule = _rule("message", "contains", "err")
        assert evaluate_rule({"message": "an error occurred"}, rule) is True

    def test_contains_matches_within_a_list(self) -> None:
        rule = _rule("tags", "contains", "urgent")
        assert evaluate_rule({"tags": ["urgent", "billing"]}, rule) is True

    def test_contains_mismatches_when_absent(self) -> None:
        rule = _rule("message", "contains", "zzz")
        assert evaluate_rule({"message": "an error occurred"}, rule) is False

    def test_contains_on_a_value_without_contains_support_is_false(self) -> None:
        # An int has no __contains__ -- the operator must not raise, just fail closed.
        rule = _rule("count", "contains", 1)
        assert evaluate_rule({"count": 42}, rule) is False

    def test_gt_matches(self) -> None:
        assert evaluate_rule({"count": 5}, _rule("count", "gt", 3)) is True

    def test_gt_mismatches(self) -> None:
        assert evaluate_rule({"count": 2}, _rule("count", "gt", 3)) is False

    def test_lt_matches(self) -> None:
        assert evaluate_rule({"count": 2}, _rule("count", "lt", 3)) is True

    def test_lt_mismatches(self) -> None:
        assert evaluate_rule({"count": 5}, _rule("count", "lt", 3)) is False

    def test_exists_true_when_field_present(self) -> None:
        assert evaluate_rule({"status": "open"}, _rule("status", "exists")) is True

    def test_exists_false_when_field_absent(self) -> None:
        assert evaluate_rule({}, _rule("status", "exists")) is False

    def test_exists_false_when_field_value_is_none(self) -> None:
        assert evaluate_rule({"status": None}, _rule("status", "exists")) is False

    def test_resolves_a_dotted_field_path(self) -> None:
        attrs = {"address": {"city": "NYC"}}
        assert evaluate_rule(attrs, _rule("address.city", "eq", "NYC")) is True

    @pytest.mark.parametrize("operator", ["eq", "ne", "in", "not_in", "contains", "gt", "lt"])
    def test_a_missing_field_always_fails_non_exists_operators(self, operator: str) -> None:
        rule = _rule("missing", operator, "anything")
        assert evaluate_rule({}, rule) is False

    def test_unrecognised_operator_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unrecognised transformation operator"):
            evaluate_rule({"status": "open"}, _rule("status", "bogus", "open"))


class TestApplyFieldMapping:
    def test_moves_a_field_to_a_new_path(self) -> None:
        result = apply_field_mapping(
            {"user": {"email": "a@example.com"}}, {"user.email": "recipient"}
        )
        assert result["recipient"] == "a@example.com"

    def test_removes_the_source_field_when_the_target_differs(self) -> None:
        result = apply_field_mapping(
            {"user": {"email": "a@example.com"}}, {"user.email": "recipient"}
        )
        assert "email" not in result["user"]

    def test_mapping_a_field_onto_itself_leaves_it_in_place(self) -> None:
        result = apply_field_mapping({"a": 1}, {"a": "a"})
        assert result == {"a": 1}

    def test_a_missing_source_path_is_skipped(self) -> None:
        result = apply_field_mapping({"other": "value"}, {"missing.path": "recipient"})
        assert "recipient" not in result

    def test_multiple_mappings_are_all_applied(self) -> None:
        result = apply_field_mapping({"a": 1, "b": 2}, {"a": "x", "b": "y"})
        assert result["x"] == 1
        assert result["y"] == 2

    def test_creates_intermediate_dicts_at_the_destination(self) -> None:
        result = apply_field_mapping({"id": "123"}, {"id": "meta.order_id"})
        assert result["meta"]["order_id"] == "123"

    def test_does_not_mutate_the_callers_original_nested_data(self) -> None:
        # Regression test for a fixed bug: moving `address.city` used to pop "city" off of
        # the caller's own original `address` dict object, because `apply_field_mapping`'s
        # shallow `dict(data)` copy shared that nested dict with the input.
        data = {"address": {"city": "NYC", "zip": "10001"}}
        apply_field_mapping(data, {"address.city": "location.city"})
        assert data == {"address": {"city": "NYC", "zip": "10001"}}


class TestApplyFiltering:
    def test_keeps_only_rows_matching_every_rule(self) -> None:
        rows = [{"status": "open", "priority": "high"}, {"status": "open", "priority": "low"}]
        rules = [_rule("status", "eq", "open"), _rule("priority", "eq", "high")]
        assert apply_filtering(rows, rules) == [{"status": "open", "priority": "high"}]

    def test_empty_rules_keeps_every_row(self) -> None:
        rows = [{"a": 1}, {"a": 2}]
        assert apply_filtering(rows, []) == rows

    def test_a_non_matching_row_is_excluded(self) -> None:
        rows = [{"status": "closed"}]
        assert apply_filtering(rows, [_rule("status", "eq", "open")]) == []

    def test_an_unrecognised_operator_in_a_rule_propagates_the_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unrecognised transformation operator"):
            apply_filtering([{"status": "open"}], [_rule("status", "bogus", "open")])


class TestApplyEnrichment:
    def test_adds_a_missing_field(self) -> None:
        assert apply_enrichment({}, {"source": "integration-hub"})["source"] == "integration-hub"

    def test_never_overwrites_an_existing_value(self) -> None:
        result = apply_enrichment({"source": "original"}, {"source": "overwritten"})
        assert result["source"] == "original"

    def test_never_overwrites_an_existing_falsy_value(self) -> None:
        # `_resolve_path(...) is None` is the only skip condition -- 0/""/False are all
        # "present" values that must not be clobbered by enrichment.
        assert apply_enrichment({"count": 0}, {"count": 99})["count"] == 0
        assert apply_enrichment({"active": False}, {"active": True})["active"] is False
        assert apply_enrichment({"name": ""}, {"name": "default"})["name"] == ""

    def test_adds_a_nested_field_creating_intermediate_dicts(self) -> None:
        result = apply_enrichment({}, {"meta.version": "v1"})
        assert result["meta"]["version"] == "v1"

    def test_multiple_fields_are_all_considered(self) -> None:
        result = apply_enrichment({"a": "existing"}, {"a": "new", "b": "added"})
        assert result == {"a": "existing", "b": "added"}

    def test_does_not_mutate_the_callers_original_nested_data(self) -> None:
        # Regression test for a fixed bug: enriching `address.zip` used to write straight
        # into the caller's own original `address` dict object once it already existed.
        data = {"address": {"city": "NYC"}}
        apply_enrichment(data, {"address.zip": "10001"})
        assert data == {"address": {"city": "NYC"}}


class TestApplyAggregation:
    _rows: ClassVar = [
        {"category": "electronics", "amount": 10},
        {"category": "electronics", "amount": 20},
        {"category": "books", "amount": 5},
    ]

    def test_sums_a_field_per_group(self) -> None:
        result = apply_aggregation(self._rows, group_by="category", aggregations={"amount": "sum"})
        by_category = {entry["category"]: entry["amount"] for entry in result}
        assert by_category == {"electronics": 30, "books": 5}

    def test_averages_a_field_per_group(self) -> None:
        result = apply_aggregation(self._rows, group_by="category", aggregations={"amount": "avg"})
        by_category = {entry["category"]: entry["amount"] for entry in result}
        assert by_category == {"electronics": 15.0, "books": 5.0}

    def test_counts_non_null_values_of_a_specific_field(self) -> None:
        rows = [{"category": "a", "amount": 1}, {"category": "a", "amount": None}]
        result = apply_aggregation(rows, group_by="category", aggregations={"amount": "count"})
        assert result[0]["amount"] == 1

    def test_min_and_max_per_group(self) -> None:
        result = apply_aggregation(self._rows, group_by="category", aggregations={"amount": "min"})
        by_category = {entry["category"]: entry["amount"] for entry in result}
        assert by_category["electronics"] == 10

        result = apply_aggregation(self._rows, group_by="category", aggregations={"amount": "max"})
        by_category = {entry["category"]: entry["amount"] for entry in result}
        assert by_category["electronics"] == 20

    def test_every_group_entry_carries_its_own_row_count(self) -> None:
        result = apply_aggregation(self._rows, group_by="category", aggregations={})
        by_category = {entry["category"]: entry["count"] for entry in result}
        assert by_category == {"electronics": 2, "books": 1}

    def test_groups_by_a_dotted_nested_path(self) -> None:
        rows = [{"meta": {"region": "us"}, "amount": 1}, {"meta": {"region": "eu"}, "amount": 2}]
        result = apply_aggregation(rows, group_by="meta.region", aggregations={"amount": "sum"})
        by_region = {entry["meta.region"]: entry["amount"] for entry in result}
        assert by_region == {"us": 1, "eu": 2}

    def test_a_field_absent_on_every_row_in_a_group_aggregates_to_none(self) -> None:
        result = apply_aggregation(self._rows, group_by="category", aggregations={"missing": "sum"})
        assert all(entry["missing"] is None for entry in result)

    def test_a_field_absent_on_every_row_counts_to_zero(self) -> None:
        result = apply_aggregation(
            self._rows, group_by="category", aggregations={"missing": "count"}
        )
        assert all(entry["missing"] == 0 for entry in result)

    def test_an_unrecognised_operation_name_is_silently_omitted_from_the_entry(self) -> None:
        result = apply_aggregation(
            self._rows, group_by="category", aggregations={"amount": "median"}
        )
        assert all("amount" not in entry for entry in result)


class TestApplyNormalization:
    def test_lowercases_a_string_field(self) -> None:
        assert apply_normalization({"a": "HELLO"}, {"a": "lowercase"})["a"] == "hello"

    def test_uppercases_a_string_field(self) -> None:
        assert apply_normalization({"a": "hello"}, {"a": "uppercase"})["a"] == "HELLO"

    def test_trims_a_string_field(self) -> None:
        assert apply_normalization({"a": "  hi  "}, {"a": "trim"})["a"] == "hi"

    def test_stringifies_a_non_string_field(self) -> None:
        assert apply_normalization({"a": 5}, {"a": "stringify"})["a"] == "5"

    def test_lowercase_uppercase_and_trim_are_no_ops_on_a_non_string_value(self) -> None:
        assert apply_normalization({"a": 5}, {"a": "lowercase"})["a"] == 5
        assert apply_normalization({"a": 5}, {"a": "uppercase"})["a"] == 5
        assert apply_normalization({"a": 5}, {"a": "trim"})["a"] == 5

    def test_a_missing_field_is_skipped(self) -> None:
        assert apply_normalization({}, {"a": "lowercase"}) == {}

    def test_an_unrecognised_rule_name_leaves_the_value_unchanged(self) -> None:
        assert apply_normalization({"a": "X"}, {"a": "unknown_rule"})["a"] == "X"

    def test_does_not_mutate_the_callers_original_nested_data(self) -> None:
        # Regression test for a fixed bug: normalizing `address.city` used to write
        # straight into the caller's own original `address` dict object.
        data = {"address": {"city": "NYC"}}
        apply_normalization(data, {"address.city": "lowercase"})
        assert data == {"address": {"city": "NYC"}}


class TestValidateSchema:
    def test_reports_a_missing_required_field(self) -> None:
        violations = validate_schema({"name": "Ada"}, {"required": ["name", "age"]})
        assert violations == ["Missing required field: age"]

    def test_a_present_required_field_has_no_violation(self) -> None:
        assert validate_schema({"name": "Ada"}, {"required": ["name"]}) == []

    def test_reports_a_type_mismatch(self) -> None:
        violations = validate_schema(
            {"age": "not-a-number"}, {"properties": {"age": {"type": "integer"}}}
        )
        assert violations == ["Field 'age' expected type 'integer', got 'str'"]

    def test_a_matching_type_has_no_violation(self) -> None:
        violations = validate_schema({"age": 30}, {"properties": {"age": {"type": "integer"}}})
        assert violations == []

    def test_a_field_absent_from_data_is_not_type_checked(self) -> None:
        assert validate_schema({}, {"properties": {"age": {"type": "integer"}}}) == []

    def test_an_unrecognised_type_name_is_never_reported_as_a_violation(self) -> None:
        violations = validate_schema(
            {"age": 5}, {"properties": {"age": {"type": "not_a_real_type"}}}
        )
        assert violations == []

    def test_a_fully_valid_document_has_no_violations(self) -> None:
        schema = {
            "required": ["name"],
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }
        assert validate_schema({"name": "Ada", "age": 30}, schema) == []

    def test_number_type_accepts_both_int_and_float(self) -> None:
        assert validate_schema({"a": 1}, {"properties": {"a": {"type": "number"}}}) == []
        assert validate_schema({"a": 1.5}, {"properties": {"a": {"type": "number"}}}) == []


class TestApplyTransformation:
    def test_dispatches_field_mapping(self) -> None:
        result = apply_transformation(
            {"a": 1}, kind=TransformationKind.FIELD_MAPPING, config={"mapping": {"a": "b"}}
        )
        assert result == {"b": 1}

    def test_dispatches_schema_validation(self) -> None:
        result = apply_transformation(
            {}, kind=TransformationKind.SCHEMA_VALIDATION, config={"schema": {"required": ["a"]}}
        )
        assert result == {"violations": ["Missing required field: a"]}

    def test_dispatches_enrichment(self) -> None:
        result = apply_transformation(
            {}, kind=TransformationKind.ENRICHMENT, config={"fields": {"a": 1}}
        )
        assert result == {"a": 1}

    def test_dispatches_filtering(self) -> None:
        result = apply_transformation(
            [{"a": 1}, {"a": 2}],
            kind=TransformationKind.FILTERING,
            config={"rules": [_rule("a", "eq", 1)]},
        )
        assert result == [{"a": 1}]

    def test_dispatches_aggregation(self) -> None:
        rows = [{"cat": "x", "amount": 1}, {"cat": "x", "amount": 2}]
        result = apply_transformation(
            rows,
            kind=TransformationKind.AGGREGATION,
            config={"group_by": "cat", "aggregations": {"amount": "sum"}},
        )
        assert result == [{"cat": "x", "count": 2, "amount": 3}]

    def test_dispatches_normalization(self) -> None:
        result = apply_transformation(
            {"a": "HI"}, kind=TransformationKind.NORMALIZATION, config={"rules": {"a": "lowercase"}}
        )
        assert result == {"a": "hi"}

    def test_dispatches_format_conversion_parsing_a_string_input(self) -> None:
        result = apply_transformation(
            '{"a": 1}',
            kind=TransformationKind.FORMAT_CONVERSION,
            config={"source_format": "json", "target_format": "yaml"},
        )
        assert result.strip() == "a: 1"

    def test_format_conversion_skips_parsing_when_data_is_already_structured(self) -> None:
        result = apply_transformation(
            {"a": 1}, kind=TransformationKind.FORMAT_CONVERSION, config={"target_format": "yaml"}
        )
        assert result.strip() == "a: 1"

    def test_format_conversion_defaults_both_formats_to_json(self) -> None:
        result = apply_transformation({}, kind=TransformationKind.FORMAT_CONVERSION, config={})
        assert result == "{}"
