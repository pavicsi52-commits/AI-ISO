"""Tests for the validation framework core.

Covers base, context, results, validator, manager, and pipeline.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions import AIIOSException
from shared_core.validation import (
    LayerStep,
    PipelineResult,
    ValidationContext,
    ValidationFrameworkConstants,
    ValidationLayer,
    ValidationManager,
    ValidationPipeline,
    ValidationPipelineError,
    ValidationResult,
    ValidationSeverity,
    Validator,
    ValidatorNotFoundError,
)

# --- base ---


def test_validation_layer_matches_the_spec_order() -> None:
    assert list(ValidationLayer) == [
        ValidationLayer.ENVIRONMENT,
        ValidationLayer.CONFIGURATION,
        ValidationLayer.API,
        ValidationLayer.SCHEMA,
        ValidationLayer.BUSINESS,
        ValidationLayer.DATABASE,
        ValidationLayer.PERMISSION,
        ValidationLayer.WORKFLOW,
        ValidationLayer.RESPONSE,
    ]


def test_layer_order_constant_matches_the_enum() -> None:
    expected = tuple(layer.value for layer in ValidationLayer)

    assert expected == ValidationFrameworkConstants.LAYER_ORDER


# --- context ---


def test_validation_context_defaults_to_english_locale() -> None:
    context = ValidationContext()

    assert context.locale == "en"
    assert context.extra == {}


def test_validation_context_with_extra_merges_fields() -> None:
    context = ValidationContext(extra={"a": 1})

    merged = context.with_extra(b=2)

    assert merged.extra == {"a": 1, "b": 2}
    assert context.extra == {"a": 1}  # original untouched


def test_validation_context_carries_tenant_scope() -> None:
    org_id = uuid4()
    context = ValidationContext(organization_id=org_id, locale="es")

    assert context.organization_id == org_id
    assert context.locale == "es"


# --- results ---


def test_validation_result_ok_defaults() -> None:
    result = ValidationResult.ok()

    assert result.valid is True
    assert result.errors == []
    assert result.severity == ValidationSeverity.INFO


def test_validation_result_fail_defaults() -> None:
    result = ValidationResult.fail("bad")

    assert result.valid is False
    assert result.errors == ["bad"]
    assert result.severity == ValidationSeverity.ERROR


def test_validation_result_fail_accepts_custom_severity() -> None:
    result = ValidationResult.fail("careful", severity=ValidationSeverity.WARNING)

    assert result.severity == ValidationSeverity.WARNING


def test_pipeline_result_errors_property_flattens_every_layer() -> None:
    result = PipelineResult(
        valid=False,
        layer_results={
            "api": ValidationResult.fail("api error"),
            "schema": ValidationResult.ok(warnings=["schema warning"]),
        },
    )

    assert result.errors == ["api error"]
    assert result.warnings == ["schema warning"]


# --- validator ---


def test_validator_run_attaches_name_and_timing() -> None:
    validator = Validator(name="my_rule", func=ValidationResult.ok)

    result = validator.run()

    assert result.validator_name == "my_rule"
    assert result.execution_time_ms >= 0.0


def test_validator_run_preserves_validity_and_errors() -> None:
    validator = Validator(name="my_rule", func=lambda x: ValidationResult.fail(f"bad: {x}"))

    result = validator.run("input")

    assert result.valid is False
    assert result.errors == ["bad: input"]


# --- manager ---


def test_manager_register_and_run() -> None:
    manager = ValidationManager()
    manager.register(ValidationLayer.SCHEMA, "always_ok", ValidationResult.ok)

    result = manager.run(ValidationLayer.SCHEMA, "always_ok")

    assert result.valid is True
    assert result.validator_name == "always_ok"


def test_manager_is_registered() -> None:
    manager = ValidationManager()

    assert manager.is_registered(ValidationLayer.SCHEMA, "unregistered") is False

    manager.register(ValidationLayer.SCHEMA, "known", ValidationResult.ok)

    assert manager.is_registered(ValidationLayer.SCHEMA, "known") is True


def test_manager_get_raises_for_unknown_validator() -> None:
    manager = ValidationManager()

    with pytest.raises(ValidatorNotFoundError):
        manager.get(ValidationLayer.SCHEMA, "does_not_exist")


def test_validator_not_found_error_is_an_aiios_exception() -> None:
    manager = ValidationManager()

    try:
        manager.get(ValidationLayer.SCHEMA, "nope")
    except ValidatorNotFoundError as exc:
        assert isinstance(exc, AIIOSException)


def test_manager_names_for_layer() -> None:
    manager = ValidationManager()
    manager.register(ValidationLayer.SCHEMA, "rule_a", ValidationResult.ok)
    manager.register(ValidationLayer.SCHEMA, "rule_b", ValidationResult.ok)
    manager.register(ValidationLayer.API, "rule_c", ValidationResult.ok)

    names = manager.names_for_layer(ValidationLayer.SCHEMA)

    assert set(names) == {"rule_a", "rule_b"}


# --- pipeline ---


def test_pipeline_runs_steps_in_order_and_succeeds() -> None:
    manager = ValidationManager()
    manager.register(ValidationLayer.API, "ok", ValidationResult.ok)
    manager.register(ValidationLayer.SCHEMA, "ok2", ValidationResult.ok)
    pipeline = ValidationPipeline(manager=manager)

    result = pipeline.run(
        [
            LayerStep(ValidationLayer.API, "ok"),
            LayerStep(ValidationLayer.SCHEMA, "ok2"),
        ]
    )

    assert result.valid is True
    assert result.failed_layer is None
    assert set(result.layer_results) == {"api", "schema"}


def test_pipeline_stops_at_the_first_failing_layer() -> None:
    manager = ValidationManager()
    manager.register(ValidationLayer.API, "fails", lambda: ValidationResult.fail("nope"))
    calls: list[str] = []

    def _should_not_run() -> ValidationResult:
        calls.append("ran")
        return ValidationResult.ok()

    manager.register(ValidationLayer.SCHEMA, "should_not_run", _should_not_run)
    pipeline = ValidationPipeline(manager=manager)

    result = pipeline.run(
        [
            LayerStep(ValidationLayer.API, "fails"),
            LayerStep(ValidationLayer.SCHEMA, "should_not_run"),
        ]
    )

    assert result.valid is False
    assert result.failed_layer == "api"
    assert calls == []
    assert "schema" not in result.layer_results


def test_pipeline_passes_args_and_kwargs_to_the_rule() -> None:
    def _echo(value: str, *, suffix: str) -> ValidationResult:
        if value == f"x{suffix}":
            return ValidationResult.ok()
        return ValidationResult.fail("no")

    manager = ValidationManager()
    manager.register(ValidationLayer.API, "echo", _echo)
    pipeline = ValidationPipeline(manager=manager)

    result = pipeline.run(
        [LayerStep(ValidationLayer.API, "echo", args=("xy",), kwargs={"suffix": "y"})]
    )

    assert result.valid is True


def test_pipeline_rejects_out_of_order_steps() -> None:
    manager = ValidationManager()
    manager.register(ValidationLayer.SCHEMA, "a", ValidationResult.ok)
    manager.register(ValidationLayer.API, "b", ValidationResult.ok)
    pipeline = ValidationPipeline(manager=manager)

    with pytest.raises(ValidationPipelineError):
        pipeline.run(
            [
                LayerStep(ValidationLayer.SCHEMA, "a"),  # schema (index 3)
                LayerStep(ValidationLayer.API, "b"),  # api (index 2) -- out of order
            ]
        )


def test_pipeline_allows_running_a_subset_of_layers_in_order() -> None:
    manager = ValidationManager()
    manager.register(ValidationLayer.BUSINESS, "b", ValidationResult.ok)
    manager.register(ValidationLayer.WORKFLOW, "w", ValidationResult.ok)
    pipeline = ValidationPipeline(manager=manager)

    result = pipeline.run(
        [
            LayerStep(ValidationLayer.BUSINESS, "b"),
            LayerStep(ValidationLayer.WORKFLOW, "w"),
        ]
    )

    assert result.valid is True


def test_pipeline_raises_validator_not_found_for_unregistered_step() -> None:
    pipeline = ValidationPipeline(manager=ValidationManager())

    with pytest.raises(ValidatorNotFoundError):
        pipeline.run([LayerStep(ValidationLayer.API, "nonexistent")])


def test_pipeline_total_execution_time_is_nonnegative() -> None:
    manager = ValidationManager()
    manager.register(ValidationLayer.API, "ok", ValidationResult.ok)
    pipeline = ValidationPipeline(manager=manager)

    result = pipeline.run([LayerStep(ValidationLayer.API, "ok")])

    assert result.total_execution_time_ms >= 0.0
    assert result.total_execution_time_ms < ValidationFrameworkConstants.MAX_PIPELINE_LATENCY_MS
