"""Tests for :class:`app.scanners.cloud.gcp_provider.GcpProvider`.

No real GCP project is reachable in this environment (see the
provider's own module docstring) -- every branch here is exercised
with ``pytest-httpx`` against the real JWT-bearer OAuth2 exchange and
Compute/Storage/SQL/GKE REST request/response logic. The JWT assertion
is signed with a real, freshly-generated RSA key (matching
``tests/conftest.py``'s own ``jwt_keypair`` fixture precedent) so the
signing step itself is genuinely exercised, not stubbed.
"""

from __future__ import annotations

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pytest_httpx import HTTPXMock

from app.scanners.base import ScanCredential
from app.scanners.cloud.gcp_provider import GcpProvider
from app.scanners.enumeration import EnumerationError

_TIMEOUT_SECONDS = 10.0
_PROJECT_ID = "aiios-test-project"
_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")


def _credential() -> ScanCredential:
    return ScanCredential(
        private_key=_private_key_pem(),
        extra={"project_id": _PROJECT_ID, "client_email": "svc@aiios-test.iam.gserviceaccount.com"},
    )


def _mock_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=_TOKEN_URI, json={"access_token": "a-real-looking-token"}
    )


async def test_enumerate_requires_credential() -> None:
    with pytest.raises(EnumerationError, match="service-account credential"):
        await GcpProvider().enumerate("proj", credential=None, timeout_seconds=_TIMEOUT_SECONDS)


async def test_enumerate_requires_project_id_and_client_email() -> None:
    credential = ScanCredential(private_key=_private_key_pem())
    with pytest.raises(EnumerationError, match="project_id"):
        await GcpProvider().enumerate(
            "proj", credential=credential, timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_lists_every_resource_type(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    compute_base = f"https://compute.googleapis.com/compute/v1/projects/{_PROJECT_ID}"
    httpx_mock.add_response(
        method="GET", url=f"{compute_base}/zones", json={"items": [{"name": "us-central1-a"}]}
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{compute_base}/aggregated/instances",
        json={"items": {"zones/us-central1-a": {"instances": [{"name": "vm-1", "id": "1"}]}}},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{compute_base}/aggregated/subnetworks",
        json={"items": {"regions/us-central1": {"subnetworks": [{"name": "subnet-1"}]}}},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{compute_base}/aggregated/firewalls",
        json={"items": {"global": {"firewalls": [{"name": "fw-1"}]}}},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{compute_base}/aggregated/forwardingRules",
        json={"items": {"regions/us-central1": {"forwardingRules": [{"name": "fr-1"}]}}},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{compute_base}/global/networks",
        json={"items": [{"name": "default"}]},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"https://storage.googleapis.com/storage/v1/b?project={_PROJECT_ID}",
        json={"items": [{"name": "aiios-test-bucket"}]},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{_PROJECT_ID}/instances",
        json={"items": [{"name": "sql-1", "databaseVersion": "POSTGRES_15"}]},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"https://container.googleapis.com/v1/projects/{_PROJECT_ID}/locations/-/clusters",
        json={"clusters": [{"name": "gke-1"}]},
    )

    resources = await GcpProvider().enumerate(
        "proj", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
    )
    names = {resource.name for resource in resources}
    assert names == {
        "us-central1-a",
        "vm-1",
        "subnet-1",
        "fw-1",
        "fr-1",
        "default",
        "aiios-test-bucket",
        "sql-1",
        "gke-1",
    }
    sql_instance = next(r for r in resources if r.name == "sql-1")
    assert sql_instance.identity["database_version"] == "POSTGRES_15"


async def test_enumerate_token_endpoint_unreachable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with pytest.raises(EnumerationError, match="token endpoint unreachable"):
        await GcpProvider().enumerate(
            "proj", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_token_request_denied(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_TOKEN_URI, status_code=401)
    with pytest.raises(EnumerationError, match="GCP authentication failed"):
        await GcpProvider().enumerate(
            "proj", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_token_response_missing_access_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_TOKEN_URI, json={})
    with pytest.raises(EnumerationError, match="did not contain an access_token"):
        await GcpProvider().enumerate(
            "proj", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_401_raises_enumeration_error(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    httpx_mock.add_response(method="GET", status_code=401)
    with pytest.raises(EnumerationError, match="GCP authorization failed"):
        await GcpProvider().enumerate(
            "proj", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_non_200_returns_empty_for_that_resource(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    for _ in range(9):
        httpx_mock.add_response(method="GET", status_code=404)
    resources = await GcpProvider().enumerate(
        "proj", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
    )
    assert resources == []


async def test_enumerate_request_unreachable(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with pytest.raises(EnumerationError, match="GCP request"):
        await GcpProvider().enumerate(
            "proj", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )
