"""``secret_providers`` table. Per docs/035 "SECRET PROVIDERS": Internal
Vault, HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Google
Secret Manager, CyberArk, External Plugin Providers, Provider
Abstraction Layer.

:attr:`config` holds connection details only (endpoint URLs, region,
mount paths) -- never credentials for reaching the external provider
itself, which is a chicken-and-egg problem this service resolves the
same way every secrets manager does: the provider's own connection
secret (e.g. an AWS IAM role or a Vault token) is itself stored as a
:class:`~app.models.secret.Secret` and referenced by id, not embedded
here in plaintext.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ProviderType


class SecretProvider(BaseModel):
    """One external (or internal) secret provider configuration."""

    __tablename__ = "secret_providers"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_secret_provider_name"),)

    name: Mapped[str] = mapped_column(String(255))
    provider_type: Mapped[ProviderType] = mapped_column(String(32), index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    connection_secret_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("secret_vault.id", ondelete="SET NULL"), default=None
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["SecretProvider"]
