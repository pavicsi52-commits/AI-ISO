"""``plugin_packages``."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PackageFormat, SignatureAlgorithm


class PluginPackage(BaseModel):
    """``plugin_packages`` -- one version's own packaged, signed artifact.

    Packaging (tar/zip + checksum) is a genuine gap -- no
    ``shared_core.plugins`` module compresses or checksums anything, so
    ``app/packages/`` builds it fresh. Storage itself reuses
    ``shared_core.storage.wrapper.StorageWrapper`` (MinIO), keyed by
    ``storage_key`` here. Signing follows ``playbook-service``'s own
    Ed25519 ``sign_checksum``/``verify_signature`` precedent, not
    ``shared_core.plugins.manifest``'s RSA-PSS scheme.
    """

    __tablename__ = "plugin_packages"
    __table_args__ = (
        UniqueConstraint("plugin_version_id", name="uq_plugin_package_version"),
        Index("ix_plugin_package_checksum", "checksum"),
    )

    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    plugin_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugin_versions.id", ondelete="CASCADE"), index=True
    )
    package_format: Mapped[PackageFormat] = mapped_column(String(16), default=PackageFormat.TAR_GZ)
    storage_key: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(128), index=True)
    """SHA-256 hex digest of the packaged artifact's own bytes."""
    signature_algorithm: Mapped[SignatureAlgorithm | None] = mapped_column(String(16), default=None)
    signature: Mapped[str | None] = mapped_column(String(1024), default=None)
    signer_id: Mapped[str | None] = mapped_column(String(128), default=None)
    signer_key_fingerprint: Mapped[str | None] = mapped_column(String(128), default=None)
    signature_verified: Mapped[bool | None] = mapped_column(Boolean, default=None)


__all__ = ["PluginPackage"]
