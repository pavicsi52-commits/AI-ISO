"""Kubernetes manifest structural validation.

Per docs/039 "KUBERNETES" "Support": YAML Manifests, Helm Charts,
Kustomize, Namespaces, ConfigMaps, Secrets References, Resource
Validation. This module checks the minimum shape every Kubernetes API
object requires (``apiVersion``/``kind``/``metadata.name``), the
minimum a Helm ``Chart.yaml`` requires, and the minimum a Kustomize
``kustomization.yaml`` requires, without pulling in a Kubernetes client
SDK or the Helm/Kustomize binaries themselves.
"""

from __future__ import annotations

from typing import Any

from app.models.enums import ManifestFormat


class KubernetesValidationError(Exception):
    """A Kubernetes manifest's content does not match its declared format."""


def validate_kubernetes_manifest(
    manifest_format: ManifestFormat, content: dict[str, Any]
) -> list[str]:
    """Return every structural problem found in *content*; empty if valid."""
    if manifest_format is ManifestFormat.YAML_MANIFEST:
        return _validate_resource(content)
    if manifest_format is ManifestFormat.HELM_CHART:
        return _require_keys(content, "Helm chart", "apiVersion", "name", "version")
    if manifest_format is ManifestFormat.KUSTOMIZE:
        errors = _require_keys(content, "kustomization", "resources")
        kind = content.get("kind")
        if kind is not None and kind != "Kustomization":
            errors.append(f"kustomization 'kind' must be 'Kustomization', got {kind!r}")
        return errors
    raise AssertionError(f"Unhandled manifest format: {manifest_format!r}")  # pragma: no cover


def validate_kubernetes_manifest_or_raise(
    manifest_format: ManifestFormat, content: dict[str, Any]
) -> None:
    """Raise :class:`KubernetesValidationError` if *content* is structurally invalid."""
    errors = validate_kubernetes_manifest(manifest_format, content)
    if errors:
        raise KubernetesValidationError("; ".join(errors))


def _validate_resource(content: dict[str, Any]) -> list[str]:
    errors = _require_keys(content, "Kubernetes resource", "apiVersion", "kind", "metadata")
    metadata = content.get("metadata")
    if isinstance(metadata, dict) and "name" not in metadata:
        errors.append("Kubernetes resource metadata is missing required key: name")
    return errors


def _require_keys(content: dict[str, Any], label: str, *keys: str) -> list[str]:
    missing = [key for key in keys if key not in content]
    if not missing:
        return []
    return [f"{label} is missing required key(s): {', '.join(missing)}"]


__all__ = [
    "KubernetesValidationError",
    "validate_kubernetes_manifest",
    "validate_kubernetes_manifest_or_raise",
]
