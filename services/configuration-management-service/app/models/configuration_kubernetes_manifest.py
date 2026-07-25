"""``configuration_kubernetes_manifests`` table. Per docs/039
"KUBERNETES" "Support": YAML Manifests, Helm Charts, Kustomize,
Namespaces, ConfigMaps, Secrets References, Resource Validation.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ManifestFormat


class ConfigurationKubernetesManifest(BaseModel):
    """One Kubernetes manifest (YAML/Helm/Kustomize) backing a configuration profile."""

    __tablename__ = "configuration_kubernetes_manifests"

    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="SET NULL"), default=None, index=True
    )
    format: Mapped[ManifestFormat] = mapped_column(String(16), index=True)
    namespace: Mapped[str | None] = mapped_column(String(255), default=None)
    name: Mapped[str] = mapped_column(String(255), index=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_errors: Mapped[list[str] | None] = mapped_column(JSON, default=None)


__all__ = ["ConfigurationKubernetesManifest"]
