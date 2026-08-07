"""HTTP-level tests for ``app/api/publishers.py`` (``/plugins/publishers``)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.models.enums import PublisherType
from app.security.signer import compute_fingerprint, generate_signing_keypair
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    AuthHeadersFn,
)


async def _register_publisher(
    client: AsyncClient, organization_id: uuid.UUID, *, slug: str = "acme-labs", **kwargs
):
    payload = {"slug": slug, "display_name": "Acme Labs", **kwargs}
    response = await client.post(
        "/plugins/publishers", params={"organization_id": str(organization_id)}, json=payload
    )
    assert response.status_code == HTTP_CREATED, response.text
    return response.json()["data"]


async def test_register_publisher_minimal(client: AsyncClient, organization_id: uuid.UUID) -> None:
    data = await _register_publisher(client, organization_id, slug="minimal-publisher")

    assert data["slug"] == "minimal-publisher"
    assert data["display_name"] == "Acme Labs"
    assert data["organization_id"] == str(organization_id)
    assert data["publisher_type"] == "individual"
    assert data["verification_status"] == "unverified"
    assert data["trusted_signing_key_fingerprint"] is None
    assert data["published_plugin_count"] == 0
    assert uuid.UUID(data["id"])


async def test_register_publisher_with_all_fields(
    client: AsyncClient, organization_id: uuid.UUID
) -> None:
    data = await _register_publisher(
        client,
        organization_id,
        slug="full-publisher",
        publisher_type=PublisherType.ORGANIZATION.value,
        contact_email="hello@acme.example",
        website_url="https://acme.example",
        bio="We build plugins.",
    )

    assert data["publisher_type"] == "organization"
    assert data["contact_email"] == "hello@acme.example"
    assert data["website_url"] == "https://acme.example"


async def test_register_publisher_duplicate_slug_returns_error(
    client: AsyncClient, organization_id: uuid.UUID
) -> None:
    await _register_publisher(client, organization_id, slug="dup-slug")

    dup = await client.post(
        "/plugins/publishers",
        params={"organization_id": str(organization_id)},
        json={"slug": "dup-slug", "display_name": "Another Name"},
    )
    assert dup.status_code >= HTTP_BAD_REQUEST, dup.text
    assert dup.status_code == HTTP_BAD_REQUEST


async def test_list_publishers_scoped_to_organization(
    client: AsyncClient, organization_id: uuid.UUID
) -> None:
    first = await _register_publisher(client, organization_id, slug="listed-one")
    second = await _register_publisher(client, organization_id, slug="listed-two")

    listed = await client.get(
        "/plugins/publishers", params={"organization_id": str(organization_id)}
    )
    assert listed.status_code == HTTP_OK
    ids = {row["id"] for row in listed.json()["data"]}
    assert {first["id"], second["id"]} <= ids

    other_org = uuid.uuid4()
    other_listed = await client.get(
        "/plugins/publishers", params={"organization_id": str(other_org)}
    )
    assert other_listed.status_code == HTTP_OK
    other_ids = {row["id"] for row in other_listed.json()["data"]}
    assert first["id"] not in other_ids
    assert second["id"] not in other_ids


async def test_get_publisher_by_id(client: AsyncClient, organization_id: uuid.UUID) -> None:
    created = await _register_publisher(client, organization_id, slug="get-me")

    found = await client.get(
        f"/plugins/publishers/{created['id']}",
        params={"organization_id": str(organization_id)},
    )
    assert found.status_code == HTTP_OK
    assert found.json()["data"]["id"] == created["id"]
    assert found.json()["data"]["slug"] == "get-me"


async def test_get_publisher_not_found(client: AsyncClient, organization_id: uuid.UUID) -> None:
    missing = await client.get(
        f"/plugins/publishers/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
    )
    assert missing.status_code == HTTP_NOT_FOUND


async def test_request_verification_moves_to_pending(
    client: AsyncClient, organization_id: uuid.UUID
) -> None:
    created = await _register_publisher(client, organization_id, slug="request-verify")

    response = await client.post(
        f"/plugins/publishers/{created['id']}/verification-requests",
        params={"organization_id": str(organization_id)},
    )
    assert response.status_code == HTTP_CREATED, response.text
    assert response.json()["data"]["verification_status"] == "pending"


async def test_request_verification_not_found(
    client: AsyncClient, organization_id: uuid.UUID
) -> None:
    response = await client.post(
        f"/plugins/publishers/{uuid.uuid4()}/verification-requests",
        params={"organization_id": str(organization_id)},
    )
    assert response.status_code == HTTP_NOT_FOUND


async def test_verify_publisher_requires_auth(
    client: AsyncClient, organization_id: uuid.UUID
) -> None:
    created = await _register_publisher(client, organization_id, slug="needs-auth")

    response = await client.post(
        f"/plugins/publishers/{created['id']}/verify",
        params={"organization_id": str(organization_id)},
    )
    assert response.status_code == HTTP_UNAUTHORIZED


async def test_verify_publisher_marks_verified(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    created = await _register_publisher(client, organization_id, slug="verify-me")
    headers = auth_headers(uuid.uuid4())

    response = await client.post(
        f"/plugins/publishers/{created['id']}/verify",
        params={"organization_id": str(organization_id)},
        headers=headers,
    )
    assert response.status_code == HTTP_OK, response.text
    assert response.json()["data"]["verification_status"] == "verified"


async def test_revoke_verification_after_verified(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    created = await _register_publisher(client, organization_id, slug="revoke-me")
    headers = auth_headers(uuid.uuid4())

    verified = await client.post(
        f"/plugins/publishers/{created['id']}/verify",
        params={"organization_id": str(organization_id)},
        headers=headers,
    )
    assert verified.status_code == HTTP_OK, verified.text

    revoked = await client.post(
        f"/plugins/publishers/{created['id']}/revoke-verification",
        params={"organization_id": str(organization_id)},
    )
    assert revoked.status_code == HTTP_OK, revoked.text
    assert revoked.json()["data"]["verification_status"] == "revoked"


async def test_revoke_verification_not_found(
    client: AsyncClient, organization_id: uuid.UUID
) -> None:
    response = await client.post(
        f"/plugins/publishers/{uuid.uuid4()}/revoke-verification",
        params={"organization_id": str(organization_id)},
    )
    assert response.status_code == HTTP_NOT_FOUND


async def test_set_trusted_signing_key_matches_fingerprint(
    client: AsyncClient, organization_id: uuid.UUID
) -> None:
    created = await _register_publisher(client, organization_id, slug="signing-key")
    _private_pem, public_pem = generate_signing_keypair()

    response = await client.put(
        f"/plugins/publishers/{created['id']}/trusted-signing-key",
        params={"organization_id": str(organization_id)},
        json={"public_key_pem": public_pem},
    )
    assert response.status_code == HTTP_OK, response.text
    assert response.json()["data"]["trusted_signing_key_fingerprint"] == compute_fingerprint(
        public_pem
    )


async def test_set_trusted_signing_key_not_found(
    client: AsyncClient, organization_id: uuid.UUID
) -> None:
    _private_pem, public_pem = generate_signing_keypair()

    response = await client.put(
        f"/plugins/publishers/{uuid.uuid4()}/trusted-signing-key",
        params={"organization_id": str(organization_id)},
        json={"public_key_pem": public_pem},
    )
    assert response.status_code == HTTP_NOT_FOUND


__all__: list[str] = []
