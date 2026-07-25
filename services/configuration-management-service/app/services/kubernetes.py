"""Kubernetes manifests (YAML/Helm/Kustomize).

Per docs/039 "KUBERNETES" "Support", including "Resource Validation" --
unlike TOSCA/Ansible content, an invalid Kubernetes manifest is still
persisted (:attr:`~app.models.configuration_kubernetes_manifest
.ConfigurationKubernetesManifest.validated` and ``.validation_errors``
record the outcome), matching that those two columns exist specifically
to store a validation *result*, not gate persistence on it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.kubernetes.validator import validate_kubernetes_manifest
from app.models.configuration_kubernetes_manifest import ConfigurationKubernetesManifest
from app.models.enums import ManifestFormat
from app.repositories.configuration_kubernetes_manifest import (
    ConfigurationKubernetesManifestRepository,
)


class ConfigurationKubernetesService:
    """Creates, reads, lists, and re-validates Kubernetes manifests."""

    def __init__(self, manifests: ConfigurationKubernetesManifestRepository) -> None:
        self._manifests = manifests

    async def get_by_id(self, manifest_id: UUID) -> ConfigurationKubernetesManifest:
        """Return the manifest identified by *manifest_id*.

        Raises:
            NotFoundError: If no such manifest exists.
        """
        return await self._manifests.require_by_id(manifest_id)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationKubernetesManifest]:
        """Every Kubernetes manifest backing *profile_id*."""
        return await self._manifests.list_for_profile(profile_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        profile_id: UUID | None,
        manifest_format: ManifestFormat,
        namespace: str | None,
        name: str,
        content: dict[str, Any],
    ) -> ConfigurationKubernetesManifest:
        """Define a new Kubernetes manifest, recording its validation outcome
        ("Resource Validation") rather than rejecting an invalid one.
        """
        errors = validate_kubernetes_manifest(manifest_format, content)
        return await self._manifests.create(
            ConfigurationKubernetesManifest(
                organization_id=organization_id,
                project_id=project_id,
                profile_id=profile_id,
                format=manifest_format,
                namespace=namespace,
                name=name,
                content=content,
                validated=not errors,
                validation_errors=errors or None,
            )
        )

    async def revalidate(self, manifest_id: UUID) -> ConfigurationKubernetesManifest:
        """Re-run "Resource Validation" against a manifest's current content."""
        manifest = await self.get_by_id(manifest_id)
        errors = validate_kubernetes_manifest(manifest.format, manifest.content)
        manifest.validated = not errors
        manifest.validation_errors = errors or None
        return await self._manifests.update(manifest)

    async def delete(self, manifest_id: UUID) -> None:
        """Soft-delete a Kubernetes manifest."""
        await self._manifests.delete(manifest_id)


__all__ = ["ConfigurationKubernetesService"]
