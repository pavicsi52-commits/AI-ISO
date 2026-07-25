"""Tests for ``app/api/certificate.py``."""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Callable

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from httpx import AsyncClient


def _make_self_signed_cert(*, common_name: str) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


async def test_import_certificate_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/certificates",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "no-auth",
            "certificate_type": "tls",
            "certificate_pem": _make_self_signed_cert(common_name="no-auth.aiios.local"),
        },
    )
    assert response.status_code == 401


async def test_import_and_list_certificate(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    pem = _make_self_signed_cert(common_name="api-imported.aiios.local")

    import_response = await client.post(
        "/certificates",
        json={
            "organization_id": str(org_id),
            "name": "api-imported",
            "certificate_type": "tls",
            "certificate_pem": pem,
        },
        headers=auth_headers(caller),
    )
    assert import_response.status_code == 201
    body = import_response.json()["data"]
    assert body["status"] == "valid"
    assert body["subject"] == "CN=api-imported.aiios.local"

    list_response = await client.get(
        "/certificates", params={"organization_id": str(org_id)}, headers=auth_headers(caller)
    )
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1


async def test_delete_certificate(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    pem = _make_self_signed_cert(common_name="deletable.aiios.local")
    import_response = await client.post(
        "/certificates",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "deletable",
            "certificate_type": "tls",
            "certificate_pem": pem,
        },
        headers=auth_headers(caller),
    )
    certificate_id = import_response.json()["data"]["id"]

    delete_response = await client.delete(
        f"/certificates/{certificate_id}", headers=auth_headers(caller)
    )
    assert delete_response.status_code == 200
