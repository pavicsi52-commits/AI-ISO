"""Tests for :mod:`app.kubernetes.validator`."""

from __future__ import annotations

import pytest

from app.kubernetes.validator import (
    KubernetesValidationError,
    validate_kubernetes_manifest,
    validate_kubernetes_manifest_or_raise,
)
from app.models.enums import ManifestFormat


def test_valid_yaml_manifest_has_no_errors() -> None:
    errors = validate_kubernetes_manifest(
        ManifestFormat.YAML_MANIFEST,
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "web"}},
    )
    assert errors == []


def test_yaml_manifest_missing_top_level_keys() -> None:
    errors = validate_kubernetes_manifest(ManifestFormat.YAML_MANIFEST, {"apiVersion": "v1"})
    assert any("missing required key" in error for error in errors)


def test_yaml_manifest_missing_metadata_name() -> None:
    errors = validate_kubernetes_manifest(
        ManifestFormat.YAML_MANIFEST,
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {}},
    )
    assert any("metadata is missing required key: name" in error for error in errors)


def test_valid_helm_chart_has_no_errors() -> None:
    errors = validate_kubernetes_manifest(
        ManifestFormat.HELM_CHART, {"apiVersion": "v2", "name": "web-chart", "version": "1.0.0"}
    )
    assert errors == []


def test_helm_chart_missing_keys() -> None:
    errors = validate_kubernetes_manifest(ManifestFormat.HELM_CHART, {"apiVersion": "v2"})
    assert any("missing required key" in error for error in errors)


def test_valid_kustomization_has_no_errors() -> None:
    errors = validate_kubernetes_manifest(
        ManifestFormat.KUSTOMIZE, {"resources": ["deployment.yaml"], "kind": "Kustomization"}
    )
    assert errors == []


def test_kustomization_missing_resources() -> None:
    errors = validate_kubernetes_manifest(ManifestFormat.KUSTOMIZE, {})
    assert any("resources" in error for error in errors)


def test_kustomization_wrong_kind() -> None:
    errors = validate_kubernetes_manifest(
        ManifestFormat.KUSTOMIZE, {"resources": [], "kind": "Deployment"}
    )
    assert any("must be 'Kustomization'" in error for error in errors)


def test_validate_or_raise_passes_through_valid_manifest() -> None:
    validate_kubernetes_manifest_or_raise(
        ManifestFormat.YAML_MANIFEST,
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "web"}},
    )


def test_validate_or_raise_raises_on_invalid_manifest() -> None:
    with pytest.raises(KubernetesValidationError):
        validate_kubernetes_manifest_or_raise(ManifestFormat.YAML_MANIFEST, {})
