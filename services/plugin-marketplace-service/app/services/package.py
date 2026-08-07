"""Plugin package building, storage, and signature verification (docs/059
"PACKAGING" / "SECURITY").
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.validation import ValidationError
from shared_core.storage.wrapper import StorageWrapper

from app.models.enums import PackageFormat
from app.models.package import PluginPackage
from app.packages.engine import build_package, compute_package_checksum
from app.repositories.package import PluginPackageRepository
from app.security.signer import sign_checksum, verify_signature


class PluginPackageService:
    """Packages a plugin version's own files, stores the artifact, and
    signs/verifies its checksum.
    """

    def __init__(
        self,
        packages: PluginPackageRepository,
        storage: StorageWrapper,
        *,
        bucket: str,
    ) -> None:
        self._packages = packages
        self._storage = storage
        self._bucket = bucket

    async def build_and_store(
        self,
        organization_id: UUID,
        plugin_id: UUID,
        plugin_version_id: UUID,
        *,
        files: dict[str, bytes],
        package_format: PackageFormat = PackageFormat.TAR_GZ,
        signer_id: str | None = None,
        signing_private_key_pem: str | None = None,
        signer_key_fingerprint: str | None = None,
    ) -> PluginPackage:
        """Build a real archive from *files*, upload it, and optionally sign
        its checksum with an Ed25519 private key.
        """
        archive_bytes = build_package(files, package_format=package_format)
        checksum = compute_package_checksum(archive_bytes)
        storage_key = f"{organization_id}/{plugin_id}/{plugin_version_id}.{package_format.value}"
        await self._storage.ensure_bucket(self._bucket)
        await self._storage.upload(
            self._bucket, storage_key, archive_bytes, "application/octet-stream"
        )

        signature = None
        if signing_private_key_pem is not None:
            signature = sign_checksum(checksum, private_key_pem=signing_private_key_pem)

        return await self._packages.create(
            PluginPackage(
                organization_id=organization_id,
                plugin_id=plugin_id,
                plugin_version_id=plugin_version_id,
                package_format=package_format,
                storage_key=storage_key,
                size_bytes=len(archive_bytes),
                checksum=checksum,
                signature=signature,
                signer_id=signer_id,
                signer_key_fingerprint=signer_key_fingerprint,
                signature_verified=None,
            )
        )

    async def download(self, package: PluginPackage) -> bytes:
        """Download a package's own stored archive bytes."""
        return await self._storage.download(self._bucket, package.storage_key)

    async def verify(self, package: PluginPackage, *, public_key_pem: str) -> PluginPackage:
        """Verify a package's own signature against a publisher's public key.

        Raises:
            ValidationError: If the package was never signed.
        """
        if package.signature is None:
            raise ValidationError("This package was never signed.")
        package.signature_verified = verify_signature(
            package.checksum, signature=package.signature, public_key_pem=public_key_pem
        )
        return await self._packages.update(package)

    async def get_for_version(self, plugin_version_id: UUID) -> PluginPackage | None:
        """The package for one specific plugin version, if any."""
        return await self._packages.get_for_version(plugin_version_id)


__all__ = ["PluginPackageService"]
