"""Tests for the validation factory: default manager and pipeline builders."""

from __future__ import annotations

from shared_core.validation.base import ValidationLayer
from shared_core.validation.factory import build_pipeline, create_manager_with_defaults
from shared_core.validation.pipeline import LayerStep


def test_create_manager_with_defaults_registers_field_validators() -> None:
    manager = create_manager_with_defaults()

    assert manager.is_registered(ValidationLayer.SCHEMA, "validate_email")
    assert manager.is_registered(ValidationLayer.SCHEMA, "validate_uuid")
    assert manager.is_registered(ValidationLayer.SCHEMA, "validate_cidr")


def test_create_manager_with_defaults_registers_request_validators() -> None:
    manager = create_manager_with_defaults()

    assert manager.is_registered(ValidationLayer.API, "validate_headers")
    assert manager.is_registered(ValidationLayer.API, "validate_json_body")


def test_create_manager_with_defaults_registers_response_validator() -> None:
    manager = create_manager_with_defaults()

    assert manager.is_registered(ValidationLayer.RESPONSE, "validate_response_envelope")


def test_create_manager_with_defaults_does_not_register_pluggable_rules() -> None:
    # business/database/security/workflow/connector rules take varied,
    # use-case-specific arguments and are intentionally left unregistered.
    manager = create_manager_with_defaults()

    assert manager.names_for_layer(ValidationLayer.BUSINESS) == []
    assert manager.names_for_layer(ValidationLayer.DATABASE) == []


def test_build_pipeline_without_manager_uses_defaults() -> None:
    pipeline = build_pipeline()

    result = pipeline.run(
        [LayerStep(ValidationLayer.SCHEMA, "validate_email", args=("user@example.com",))]
    )

    assert result.valid is True


def test_build_pipeline_with_explicit_manager() -> None:
    manager = create_manager_with_defaults()
    pipeline = build_pipeline(manager)

    result = pipeline.run(
        [LayerStep(ValidationLayer.SCHEMA, "validate_uuid", args=("not-a-uuid",))]
    )

    assert result.valid is False
