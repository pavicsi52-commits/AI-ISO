"""Tests for :class:`app.services.package.PluginPackageService` -- real
tar.gz building, real MinIO storage, and Ed25519 signing/verification.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.validation import ValidationError

from app.manifests.engine import compute_manifest_checksum
from app.models.enums import PackageFormat, PluginCategory, PluginType
from app.models.plugin import PluginVersion
from app.packages.engine import compute_package_checksum, extract_package
from app.security.signer import generate_signing_keypair
from app.services.package import PluginPackageService
from app.services.plugin import PluginService

FILES = {
    "manifest.json": b'{"name": "pkg"}',
    "src/main.py": b"print('hello')\n",
}


def _manifest(version: str = "1.0.0") -> dict:
    manifest = {
        "name": "Package Test Plugin",
        "publisher": "package-tests",
        "category": PluginCategory.UTILITIES.value,
        "type": PluginType.CUSTOM_PLUGIN.value,
        "version": version,
        "entry_points": ["main:run"],
        "supported_platform_versions": [
            {"platform": "aiios", "version_constraint": ">=1.0.0,<2.0.0"}
        ],
        "permissions_required": [],
        "dependencies": [],
        "api_requirements": [],
        "health_checks": [],
    }
    manifest["checksum"] = compute_manifest_checksum(manifest)
    return manifest


async def _make_version(
    plugin_service: PluginService, organization_id: uuid.UUID, slug: str
) -> tuple[uuid.UUID, PluginVersion]:
    """Register a real plugin and submit a real version for it -- both
    ``PluginPackage.plugin_id`` and ``.plugin_version_id`` are real foreign
    keys, so a package row can't be created against a made-up id.
    """
    plugin = await plugin_service.register(
        organization_id,
        slug=slug,
        name="Package Test Plugin",
        category=PluginCategory.UTILITIES,
        plugin_type=PluginType.CUSTOM_PLUGIN,
    )
    version, _manifest_entry = await plugin_service.submit_manifest(
        organization_id, plugin.id, version_number="1.0.0", manifest=_manifest()
    )
    return plugin.id, version


class TestBuildAndStore:
    async def test_build_and_store_without_signing(
        self,
        package_service: PluginPackageService,
        plugin_service: PluginService,
        organization_id: uuid.UUID,
    ) -> None:
        plugin_id, version = await _make_version(plugin_service, organization_id, "pkg-nosign")

        package = await package_service.build_and_store(
            organization_id, plugin_id, version.id, files=FILES
        )

        assert package.organization_id == organization_id
        assert package.plugin_id == plugin_id
        assert package.plugin_version_id == version.id
        assert package.package_format == PackageFormat.TAR_GZ
        assert package.storage_key == f"{organization_id}/{plugin_id}/{version.id}.tar_gz"
        assert package.size_bytes > 0
        assert package.signature is None
        assert package.signer_id is None
        assert package.signature_verified is None

        downloaded = await package_service.download(package)
        assert compute_package_checksum(downloaded) == package.checksum
        assert extract_package(downloaded, package_format=PackageFormat.TAR_GZ) == FILES

    async def test_build_and_store_with_signing(
        self,
        package_service: PluginPackageService,
        plugin_service: PluginService,
        organization_id: uuid.UUID,
    ) -> None:
        plugin_id, version = await _make_version(plugin_service, organization_id, "pkg-signed")
        private_key_pem, _public_key_pem = generate_signing_keypair()

        package = await package_service.build_and_store(
            organization_id,
            plugin_id,
            version.id,
            files=FILES,
            signer_id="publisher-1",
            signing_private_key_pem=private_key_pem,
            signer_key_fingerprint="SHA256:fake-fingerprint",
        )

        assert package.signature is not None
        assert package.signer_id == "publisher-1"
        assert package.signer_key_fingerprint == "SHA256:fake-fingerprint"
        assert package.signature_verified is None


class TestDownload:
    async def test_download_returns_exact_uploaded_bytes(
        self,
        package_service: PluginPackageService,
        plugin_service: PluginService,
        organization_id: uuid.UUID,
    ) -> None:
        plugin_id, version = await _make_version(plugin_service, organization_id, "pkg-download")
        package = await package_service.build_and_store(
            organization_id, plugin_id, version.id, files=FILES
        )

        downloaded = await package_service.download(package)

        # The checksum is computed once, at build time, over the exact
        # bytes handed to storage -- a checksum match after a real MinIO
        # round trip proves `download` returned those same bytes back.
        assert compute_package_checksum(downloaded) == package.checksum
        assert extract_package(downloaded, package_format=PackageFormat.TAR_GZ) == FILES


class TestVerify:
    async def test_verify_with_matching_public_key(
        self,
        package_service: PluginPackageService,
        plugin_service: PluginService,
        organization_id: uuid.UUID,
    ) -> None:
        plugin_id, version = await _make_version(plugin_service, organization_id, "pkg-verify-ok")
        private_key_pem, public_key_pem = generate_signing_keypair()
        package = await package_service.build_and_store(
            organization_id,
            plugin_id,
            version.id,
            files=FILES,
            signing_private_key_pem=private_key_pem,
        )

        verified = await package_service.verify(package, public_key_pem=public_key_pem)

        assert verified.signature_verified is True

    async def test_verify_with_wrong_public_key(
        self,
        package_service: PluginPackageService,
        plugin_service: PluginService,
        organization_id: uuid.UUID,
    ) -> None:
        plugin_id, version = await _make_version(plugin_service, organization_id, "pkg-verify-bad")
        private_key_pem, _correct_public_key_pem = generate_signing_keypair()
        _other_private_key_pem, wrong_public_key_pem = generate_signing_keypair()
        package = await package_service.build_and_store(
            organization_id,
            plugin_id,
            version.id,
            files=FILES,
            signing_private_key_pem=private_key_pem,
        )

        verified = await package_service.verify(package, public_key_pem=wrong_public_key_pem)

        assert verified.signature_verified is False

    async def test_verify_never_signed_raises(
        self,
        package_service: PluginPackageService,
        plugin_service: PluginService,
        organization_id: uuid.UUID,
    ) -> None:
        plugin_id, version = await _make_version(
            plugin_service, organization_id, "pkg-verify-unsigned"
        )
        package = await package_service.build_and_store(
            organization_id, plugin_id, version.id, files=FILES
        )
        _private_key_pem, public_key_pem = generate_signing_keypair()

        with pytest.raises(ValidationError, match="never signed"):
            await package_service.verify(package, public_key_pem=public_key_pem)


class TestGetForVersion:
    async def test_get_for_version_hit_and_miss(
        self,
        package_service: PluginPackageService,
        plugin_service: PluginService,
        organization_id: uuid.UUID,
    ) -> None:
        plugin_id, version = await _make_version(plugin_service, organization_id, "pkg-getver")
        package = await package_service.build_and_store(
            organization_id, plugin_id, version.id, files=FILES
        )

        found = await package_service.get_for_version(version.id)
        assert found is not None
        assert found.id == package.id

        missing = await package_service.get_for_version(uuid.uuid4())
        assert missing is None
