"""Request/response schemas for Kubernetes manifests."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ManifestFormat


class ConfigurationKubernetesManifestCreateRequest(BaseModel):
    """Body of ``POST /configurations/kubernetes``."""

    organization_id: UUID
    project_id: UUID | None = None
    profile_id: UUID | None = None
    format: ManifestFormat
    namespace: str | None = Field(default=None, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    content: dict[str, Any] = Field(default_factory=dict)


class ConfigurationKubernetesManifestResponse(BaseModel):
    """One Kubernetes manifest (YAML/Helm/Kustomize) backing a configuration profile."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    profile_id: UUID | None
    format: ManifestFormat
    namespace: str | None
    name: str
    content: dict[str, Any]
    validated: bool
    validation_errors: list[str] | None


__all__ = [
    "ConfigurationKubernetesManifestCreateRequest",
    "ConfigurationKubernetesManifestResponse",
]
