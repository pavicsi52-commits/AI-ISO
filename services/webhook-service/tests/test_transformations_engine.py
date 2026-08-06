"""Pure tests for app/transformations/engine.py -- no database, no fixtures.

`_jinja_env` is a module-level `SandboxedEnvironment` singleton shared across
every test in the process -- nothing here monkeypatches it, so there is
nothing to restore between tests.
"""

from __future__ import annotations

import jinja2
import pytest
from jinja2.exceptions import SecurityError

from app.models.enums import TransformationKind
from app.transformations.engine import (
    _delete_path,
    _get_path,
    _set_path,
    apply_field_enrichment,
    apply_field_removal,
    apply_field_rename,
    apply_header_mapping,
    apply_json_mapping,
    apply_metadata_injection,
    apply_template_rendering,
    apply_transformation,
    apply_version_conversion,
    render_template,
)


class TestGetPath:
    def test_top_level_key(self) -> None:
        assert _get_path({"a": 1}, "a") == 1

    def test_nested_key(self) -> None:
        assert _get_path({"a": {"b": 2}}, "a.b") == 2

    def test_missing_key_returns_none(self) -> None:
        assert _get_path({"a": 1}, "missing") is None

    def test_intermediate_non_dict_returns_none(self) -> None:
        assert _get_path({"a": 1}, "a.b") is None


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

    def test_non_dict_intermediate_value_is_a_silent_no_op(self) -> None:
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


class TestApplyJsonMapping:
    def test_maps_a_field_to_a_new_path(self) -> None:
        payload = {"user": {"email": "a@example.com"}}
        config = {"mappings": [{"from": "user.email", "to": "recipient"}]}
        result = apply_json_mapping(payload, config)
        assert result["recipient"] == "a@example.com"

    def test_original_field_is_left_in_place(self) -> None:
        payload = {"user": {"email": "a@example.com"}}
        config = {"mappings": [{"from": "user.email", "to": "recipient"}]}
        result = apply_json_mapping(payload, config)
        assert result["user"]["email"] == "a@example.com"

    def test_does_not_mutate_the_original_payload(self) -> None:
        payload = {"user": {"email": "a@example.com"}}
        config = {"mappings": [{"from": "user.email", "to": "recipient"}]}
        apply_json_mapping(payload, config)
        assert "recipient" not in payload

    def test_skips_a_mapping_whose_source_is_missing(self) -> None:
        payload = {"other": "value"}
        config = {"mappings": [{"from": "missing.path", "to": "recipient"}]}
        result = apply_json_mapping(payload, config)
        assert "recipient" not in result

    def test_creates_intermediate_dicts_at_the_destination(self) -> None:
        payload = {"id": "123"}
        config = {"mappings": [{"from": "id", "to": "meta.order_id"}]}
        result = apply_json_mapping(payload, config)
        assert result["meta"]["order_id"] == "123"

    def test_multiple_mappings_are_all_applied(self) -> None:
        payload = {"a": 1, "b": 2}
        config = {"mappings": [{"from": "a", "to": "x"}, {"from": "b", "to": "y"}]}
        result = apply_json_mapping(payload, config)
        assert result["x"] == 1
        assert result["y"] == 2

    def test_no_mappings_configured_returns_an_equivalent_copy(self) -> None:
        payload = {"a": 1}
        assert apply_json_mapping(payload, {}) == {"a": 1}


class TestApplyHeaderMapping:
    def test_adds_new_headers(self) -> None:
        result = apply_header_mapping({}, {"add": {"X-Foo": "bar"}})
        assert result["X-Foo"] == "bar"

    def test_added_values_are_coerced_to_strings(self) -> None:
        result = apply_header_mapping({}, {"add": {"X-Count": 5}})
        assert result["X-Count"] == "5"

    def test_removes_a_header_by_exact_name(self) -> None:
        result = apply_header_mapping({"X-Foo": "bar"}, {"remove": ["X-Foo"]})
        assert "X-Foo" not in result

    def test_removal_is_case_insensitive(self) -> None:
        result = apply_header_mapping({"X-Foo": "bar"}, {"remove": ["x-foo"]})
        assert result == {}

    def test_removing_a_missing_header_is_a_no_op(self) -> None:
        result = apply_header_mapping({"X-Foo": "bar"}, {"remove": ["X-Missing"]})
        assert result == {"X-Foo": "bar"}

    def test_add_and_remove_combine(self) -> None:
        result = apply_header_mapping({"X-Old": "1"}, {"add": {"X-New": "2"}, "remove": ["X-Old"]})
        assert result == {"X-New": "2"}

    def test_does_not_mutate_the_original_headers_dict(self) -> None:
        headers = {"X-Foo": "bar"}
        apply_header_mapping(headers, {"remove": ["X-Foo"]})
        assert headers == {"X-Foo": "bar"}

    def test_empty_config_returns_an_equivalent_copy(self) -> None:
        assert apply_header_mapping({"X-Foo": "bar"}, {}) == {"X-Foo": "bar"}


class TestApplyFieldRename:
    def test_renames_a_field(self) -> None:
        payload = {"old_key": "value"}
        config = {"renames": [{"from": "old_key", "to": "new_key"}]}
        result = apply_field_rename(payload, config)
        assert result == {"new_key": "value"}

    def test_renames_a_nested_field(self) -> None:
        payload = {"user": {"old": "value"}}
        config = {"renames": [{"from": "user.old", "to": "user.new"}]}
        result = apply_field_rename(payload, config)
        assert result == {"user": {"new": "value"}}

    def test_skips_a_rename_whose_source_is_missing(self) -> None:
        payload = {"other": "value"}
        config = {"renames": [{"from": "missing", "to": "new_key"}]}
        result = apply_field_rename(payload, config)
        assert result == {"other": "value"}

    def test_multiple_renames_are_all_applied(self) -> None:
        payload = {"a": 1, "b": 2}
        config = {"renames": [{"from": "a", "to": "x"}, {"from": "b", "to": "y"}]}
        result = apply_field_rename(payload, config)
        assert result == {"x": 1, "y": 2}

    def test_does_not_mutate_the_original_payload(self) -> None:
        payload = {"old_key": "value"}
        config = {"renames": [{"from": "old_key", "to": "new_key"}]}
        apply_field_rename(payload, config)
        assert payload == {"old_key": "value"}


class TestApplyFieldRemoval:
    def test_removes_listed_fields(self) -> None:
        payload = {"a": 1, "b": 2, "c": 3}
        result = apply_field_removal(payload, {"fields": ["a", "c"]})
        assert result == {"b": 2}

    def test_removing_a_nested_field(self) -> None:
        payload = {"a": {"b": 1, "c": 2}}
        result = apply_field_removal(payload, {"fields": ["a.b"]})
        assert result == {"a": {"c": 2}}

    def test_removing_a_missing_field_does_not_raise(self) -> None:
        payload = {"a": 1}
        result = apply_field_removal(payload, {"fields": ["missing"]})
        assert result == {"a": 1}

    def test_does_not_mutate_the_original_payload(self) -> None:
        payload = {"a": 1}
        apply_field_removal(payload, {"fields": ["a"]})
        assert payload == {"a": 1}


class TestApplyFieldEnrichment:
    def test_adds_a_missing_field(self) -> None:
        result = apply_field_enrichment({}, {"fields": {"source": "webhook-service"}})
        assert result["source"] == "webhook-service"

    def test_never_overwrites_an_existing_value(self) -> None:
        payload = {"source": "original"}
        result = apply_field_enrichment(payload, {"fields": {"source": "overwritten"}})
        assert result["source"] == "original"

    def test_adds_a_nested_field(self) -> None:
        result = apply_field_enrichment({}, {"fields": {"meta.version": "v1"}})
        assert result["meta"]["version"] == "v1"

    def test_multiple_fields_are_all_considered(self) -> None:
        payload = {"a": "existing"}
        result = apply_field_enrichment(payload, {"fields": {"a": "new", "b": "added"}})
        assert result == {"a": "existing", "b": "added"}


class TestRenderTemplate:
    def test_substitutes_a_simple_variable(self) -> None:
        assert render_template("Hello {{ name }}", {"name": "Ada"}) == "Hello Ada"

    def test_can_access_nested_dict_values_via_attribute_syntax(self) -> None:
        result = render_template("{{ user.name }}", {"user": {"name": "Ada"}})
        assert result == "Ada"

    def test_a_missing_variable_renders_as_empty_rather_than_raising(self) -> None:
        assert render_template("Hi {{ missing }}!", {}) == "Hi !"

    def test_malformed_syntax_raises_a_template_error(self) -> None:
        with pytest.raises(jinja2.TemplateError):
            render_template("Hi {{ name", {"name": "Ada"})

    def test_sandbox_blocks_access_to_python_internals_via_mro(self) -> None:
        # The classic sandbox-escape probe: walking `__class__.__mro__` to reach `object`
        # and then `__subclasses__()` to find something exploitable. A plain (non-sandboxed)
        # jinja2.Environment would render this; SandboxedEnvironment must refuse it.
        with pytest.raises(SecurityError):
            render_template("{{ ''.__class__.__mro__[1].__subclasses__() }}", {})

    def test_sandbox_blocks_a_two_level_dunder_chain(self) -> None:
        # A *bare* `''.__class__` alone is caught but rendered as an inert empty Undefined
        # (nothing unsafe has happened yet -- no attribute of the real class was reached).
        # Chaining one more dunder attribute off of it is what actually triggers the stored
        # SecurityError, since `__mro__` isn't an attribute Undefined itself already has.
        with pytest.raises(SecurityError):
            render_template("{{ ''.__class__.__mro__ }}", {})

    def test_bare_dunder_attribute_access_alone_is_inert(self) -> None:
        # Documents the other half of the above: accessing (but not chaining off of) a
        # forbidden attribute renders as an empty, inert Undefined rather than raising --
        # the sandbox's protection is about reaching real internals, not the bare lookup.
        assert render_template("{{ ''.__class__ }}", {}) == ""


class TestApplyTemplateRendering:
    def test_renders_into_the_configured_target_field(self) -> None:
        payload = {"name": "Ada"}
        config = {"template": "Hello {{ name }}", "target_field": "greeting"}
        result = apply_template_rendering(payload, config)
        assert result["greeting"] == "Hello Ada"

    def test_defaults_the_target_field_to_rendered(self) -> None:
        payload = {"name": "Ada"}
        config = {"template": "Hello {{ name }}"}
        result = apply_template_rendering(payload, config)
        assert result["rendered"] == "Hello Ada"

    def test_original_payload_fields_survive_alongside_the_rendered_field(self) -> None:
        payload = {"name": "Ada"}
        config = {"template": "Hi {{ name }}"}
        result = apply_template_rendering(payload, config)
        assert result["name"] == "Ada"

    def test_a_malformed_template_propagates_the_template_error(self) -> None:
        with pytest.raises(jinja2.TemplateError):
            apply_template_rendering({}, {"template": "{{ broken"})


class TestApplyMetadataInjection:
    def test_injects_metadata_into_a_new_key(self) -> None:
        result = apply_metadata_injection({}, {"metadata": {"delivery_id": "d1"}})
        assert result["_webhook_metadata"] == {"delivery_id": "d1"}

    def test_merges_into_an_existing_metadata_dict(self) -> None:
        payload = {"_webhook_metadata": {"existing": "keep"}}
        result = apply_metadata_injection(payload, {"metadata": {"delivery_id": "d1"}})
        assert result["_webhook_metadata"] == {"existing": "keep", "delivery_id": "d1"}

    def test_missing_metadata_config_creates_an_empty_metadata_dict(self) -> None:
        result = apply_metadata_injection({}, {})
        assert result["_webhook_metadata"] == {}

    def test_does_not_mutate_the_original_payload(self) -> None:
        payload = {"a": 1}
        apply_metadata_injection(payload, {"metadata": {"x": "y"}})
        assert payload == {"a": 1}


class TestApplyVersionConversion:
    def test_sets_the_default_schema_version_field(self) -> None:
        result = apply_version_conversion({}, {"target_version": "2.0"})
        assert result["schema_version"] == "2.0"

    def test_sets_a_custom_version_field_path(self) -> None:
        result = apply_version_conversion(
            {}, {"target_version": "2.0", "version_field": "meta.version"}
        )
        assert result["meta"]["version"] == "2.0"


class TestApplyTransformation:
    def test_dispatches_json_mapping(self) -> None:
        payload = {"a": 1}
        config = {"mappings": [{"from": "a", "to": "b"}]}
        result = apply_transformation(payload, kind=TransformationKind.JSON_MAPPING, config=config)
        assert result["b"] == 1

    def test_dispatches_field_rename(self) -> None:
        payload = {"old": "v"}
        config = {"renames": [{"from": "old", "to": "new"}]}
        result = apply_transformation(payload, kind=TransformationKind.FIELD_RENAME, config=config)
        assert result == {"new": "v"}

    def test_dispatches_field_removal(self) -> None:
        payload = {"a": 1, "b": 2}
        result = apply_transformation(
            payload, kind=TransformationKind.FIELD_REMOVAL, config={"fields": ["a"]}
        )
        assert result == {"b": 2}

    def test_dispatches_field_enrichment(self) -> None:
        result = apply_transformation(
            {}, kind=TransformationKind.FIELD_ENRICHMENT, config={"fields": {"a": 1}}
        )
        assert result == {"a": 1}

    def test_dispatches_template_rendering(self) -> None:
        result = apply_transformation(
            {"name": "Ada"},
            kind=TransformationKind.TEMPLATE_RENDERING,
            config={"template": "Hi {{ name }}"},
        )
        assert result["rendered"] == "Hi Ada"

    def test_dispatches_metadata_injection(self) -> None:
        result = apply_transformation(
            {}, kind=TransformationKind.METADATA_INJECTION, config={"metadata": {"a": 1}}
        )
        assert result["_webhook_metadata"] == {"a": 1}

    def test_dispatches_version_conversion(self) -> None:
        result = apply_transformation(
            {}, kind=TransformationKind.VERSION_CONVERSION, config={"target_version": "3.0"}
        )
        assert result["schema_version"] == "3.0"

    def test_header_mapping_kind_passes_the_payload_through_unchanged(self) -> None:
        # HEADER_MAPPING is applied separately via apply_header_mapping -- it has no
        # payload-level effect through this dispatcher.
        payload = {"a": 1}
        result = apply_transformation(
            payload, kind=TransformationKind.HEADER_MAPPING, config={"add": {"X-Foo": "1"}}
        )
        assert result == {"a": 1}

    def test_custom_kind_passes_the_payload_through_unchanged(self) -> None:
        payload = {"a": 1}
        result = apply_transformation(payload, kind=TransformationKind.CUSTOM, config={})
        assert result == {"a": 1}
