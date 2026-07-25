"""Tests for :class:`app.scanners.cloud.oracle_provider.OracleProvider`.

No real OCI tenancy is reachable in this environment (see the
provider's own module docstring) -- every branch here is exercised
with ``pytest-httpx`` against the real RSA-SHA256 request-signing and
REST request/response logic. The signature is computed with a real,
freshly-generated RSA key (matching ``tests/test_scanner_gcp.py``'s own
precedent).
"""

from __future__ import annotations

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pytest_httpx import HTTPXMock

from app.scanners.base import ScanCredential
from app.scanners.cloud.oracle_provider import OracleProvider
from app.scanners.enumeration import EnumerationError

_TIMEOUT_SECONDS = 10.0
_TENANCY_OCID = "ocid1.tenancy.oc1..aaaa"
_USER_OCID = "ocid1.user.oc1..bbbb"
_REGION = "us-ashburn-1"


def _private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")


def _credential() -> ScanCredential:
    return ScanCredential(
        username=_USER_OCID,
        private_key=_private_key_pem(),
        extra={
            "tenancy_ocid": _TENANCY_OCID,
            "key_fingerprint": "aa:bb:cc:dd",
            "region": _REGION,
        },
    )


async def test_enumerate_requires_username_and_private_key() -> None:
    with pytest.raises(EnumerationError, match="user OCID"):
        await OracleProvider().enumerate("t", credential=None, timeout_seconds=_TIMEOUT_SECONDS)


async def test_enumerate_requires_tenancy_and_fingerprint() -> None:
    credential = ScanCredential(username=_USER_OCID, private_key=_private_key_pem())
    with pytest.raises(EnumerationError, match="tenancy_ocid"):
        await OracleProvider().enumerate(
            "t", credential=credential, timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_lists_every_resource_type(httpx_mock: HTTPXMock) -> None:
    # Registered with no `url=` filter, so pytest-httpx matches each
    # against the next GET request in real call order (every call
    # except "regions" also carries a compartmentId query param this
    # test doesn't need to duplicate to prove parsing works).
    names = [
        "region-1",
        "vm-1",
        "vcn-1",
        "subnet-1",
        "seclist-1",
        "lb-1",
        "adb-1",
        "oke-1",
    ]
    for name in names:
        httpx_mock.add_response(
            method="GET",
            json=[{"displayName": name, "id": f"ocid1.x.{name}", "lifecycleState": "ACTIVE"}],
        )

    resources = await OracleProvider().enumerate(
        "t", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
    )
    assert {resource.name for resource in resources} == set(names)
    instance = next(r for r in resources if r.name == "vm-1")
    assert instance.identity["lifecycle_state"] == "ACTIVE"

    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"].startswith('Signature version="1"')
    assert "rsa-sha256" in request.headers["authorization"]


async def test_enumerate_401_raises_enumeration_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", status_code=401)
    with pytest.raises(EnumerationError, match="OCI authorization failed"):
        await OracleProvider().enumerate(
            "t", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_non_200_returns_empty_for_that_resource(httpx_mock: HTTPXMock) -> None:
    for _ in range(8):
        httpx_mock.add_response(method="GET", status_code=404)
    resources = await OracleProvider().enumerate(
        "t", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
    )
    assert resources == []


async def test_enumerate_request_unreachable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with pytest.raises(EnumerationError, match="OCI request"):
        await OracleProvider().enumerate(
            "t", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )
