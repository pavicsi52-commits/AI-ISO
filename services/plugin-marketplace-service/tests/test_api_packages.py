"""HTTP-level tests for ``app/api/packages.py``
(``/plugins/{plugin_id}/versions/{version_id}/package``)."""

from __future__ import annotations

import base64
import uuid

from httpx import AsyncClient

from app.security.signer import generate_signing_keypair
from tests.conftest import HTTP_CREATED, HTTP_NOT_FOUND, HTTP_OK, AuthHeadersFn


async def _make_version(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn, *, slug: str
) -> tuple[str, str]:
    """Register a plugin and submit one version's manifest, without publishing.

    Returns ``(plugin_id, version_id)``. A package can be built against
    any submitted version -- publishing is not a precondition.
    """
    params = {"organization_id": str(organization_id)}
    registered = await client.post(
        "/plugins",
        params=params,
        json={"slug": slug, "name": slug, "category": "utilities", "plugin_type": "custom_plugin"},
        headers=auth_headers(uuid.uuid4()),
    )
    assert registered.status_code == HTTP_CREATED, registered.text
    plugin_id = registered.json()["data"]["id"]

    manifest_response = await client.post(
        f"/plugins/{plugin_id}/manifest",
        params=params,
        json={
            "version_number": "1.0.0",
            "manifest": {
                "name": slug,
                "publisher": "api-tests",
                "category": "utilities",
                "type": "custom_plugin",
                "version": "1.0.0",
                "entry_points": ["main:run"],
                "supported_platform_versions": [
                    {"platform": "aiios", "version_constraint": ">=1.0.0,<2.0.0"}
                ],
            },
        },
    )
    assert manifest_response.status_code == HTTP_CREATED, manifest_response.text

    versions = await client.get(f"/plugins/{plugin_id}/versions", params=params)
    assert versions.status_code == HTTP_OK, versions.text
    version_id = versions.json()["data"][0]["id"]
    return plugin_id, version_id


def _encoded_files() -> dict[str, str]:
    return {
        "manifest.json": base64.b64encode(b'{"name": "test"}').decode("ascii"),
        "main.py": base64.b64encode(b"print(1)\n").decode("ascii"),
    }


async def test_get_package_not_found(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    _plugin_id, version_id = await _make_version(
        client, organization_id, auth_headers, slug="package-not-found"
    )
    response = await client.get(f"/plugins/x/versions/{version_id}/package")
    assert response.status_code == HTTP_NOT_FOUND


async def test_build_and_get_package_tar_gz(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id, version_id = await _make_version(
        client, organization_id, auth_headers, slug="package-tar-gz"
    )
    built = await client.post(
        f"/plugins/{plugin_id}/versions/{version_id}/package",
        params={"organization_id": str(organization_id)},
        json={"files": _encoded_files(), "package_format": "tar_gz"},
    )
    assert built.status_code == HTTP_CREATED, built.text
    assert built.json()["data"]["package_format"] == "tar_gz"
    assert built.json()["data"]["size_bytes"] > 0
    checksum = built.json()["data"]["checksum"]
    assert len(checksum) == 64

    fetched = await client.get(f"/plugins/{plugin_id}/versions/{version_id}/package")
    assert fetched.status_code == HTTP_OK, fetched.text
    assert fetched.json()["data"]["checksum"] == checksum


async def test_build_package_zip_format(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id, version_id = await _make_version(
        client, organization_id, auth_headers, slug="package-zip"
    )
    built = await client.post(
        f"/plugins/{plugin_id}/versions/{version_id}/package",
        params={"organization_id": str(organization_id)},
        json={"files": _encoded_files(), "package_format": "zip"},
    )
    assert built.status_code == HTTP_CREATED, built.text
    assert built.json()["data"]["package_format"] == "zip"


async def test_build_signed_package_and_verify(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id, version_id = await _make_version(
        client, organization_id, auth_headers, slug="package-signed"
    )
    private_pem, public_pem = generate_signing_keypair()

    built = await client.post(
        f"/plugins/{plugin_id}/versions/{version_id}/package",
        params={"organization_id": str(organization_id)},
        json={
            "files": _encoded_files(),
            "package_format": "tar_gz",
            "signer_id": "signer-1",
            "signing_private_key_pem": private_pem,
        },
    )
    assert built.status_code == HTTP_CREATED, built.text
    assert built.json()["data"]["signature_verified"] is None

    verified = await client.post(
        f"/plugins/{plugin_id}/versions/{version_id}/package/verify",
        json={"public_key_pem": public_pem},
    )
    assert verified.status_code == HTTP_OK, verified.text
    assert verified.json()["data"]["signature_verified"] is True


async def test_verify_package_with_wrong_key_fails(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id, version_id = await _make_version(
        client, organization_id, auth_headers, slug="package-wrong-key"
    )
    private_pem, _public_pem = generate_signing_keypair()
    _other_private_pem, other_public_pem = generate_signing_keypair()

    built = await client.post(
        f"/plugins/{plugin_id}/versions/{version_id}/package",
        params={"organization_id": str(organization_id)},
        json={
            "files": _encoded_files(),
            "package_format": "tar_gz",
            "signing_private_key_pem": private_pem,
        },
    )
    assert built.status_code == HTTP_CREATED, built.text

    verified = await client.post(
        f"/plugins/{plugin_id}/versions/{version_id}/package/verify",
        json={"public_key_pem": other_public_pem},
    )
    assert verified.status_code == HTTP_OK, verified.text
    assert verified.json()["data"]["signature_verified"] is False


async def test_verify_package_never_built_returns_not_found(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    _plugin_id, version_id = await _make_version(
        client, organization_id, auth_headers, slug="package-verify-missing"
    )
    _private_pem, public_pem = generate_signing_keypair()

    response = await client.post(
        f"/plugins/x/versions/{version_id}/package/verify", json={"public_key_pem": public_pem}
    )
    assert response.status_code == HTTP_NOT_FOUND
