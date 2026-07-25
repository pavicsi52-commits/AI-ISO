"""Tests for :class:`app.scanners.cloud.ibm_provider.IbmProvider`.

No real IBM Cloud account is reachable in this environment (see the
provider's own module docstring) -- every branch here is exercised
with ``pytest-httpx`` against the real IAM API-key token exchange and
VPC/Resource-Controller/Kubernetes-Service REST request/response logic.
"""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.scanners.base import ScanCredential
from app.scanners.cloud.ibm_provider import IbmProvider
from app.scanners.enumeration import EnumerationError

_TIMEOUT_SECONDS = 10.0
_IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
_REGION = "us-south"


def _credential() -> ScanCredential:
    return ScanCredential(token="a-real-looking-api-key", extra={"region": _REGION})


def _mock_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=_IAM_TOKEN_URL, json={"access_token": "a-real-looking-token"}
    )


async def test_enumerate_requires_credential() -> None:
    with pytest.raises(EnumerationError, match="API key credential"):
        await IbmProvider().enumerate("acct", credential=None, timeout_seconds=_TIMEOUT_SECONDS)


async def test_enumerate_lists_every_resource_type(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    vpc_base = f"https://{_REGION}.iaas.cloud.ibm.com/v1"
    httpx_mock.add_response(
        method="GET",
        url=httpx.URL(f"{vpc_base}/regions").copy_merge_params(
            {"version": "2024-01-01", "generation": "2"}
        ),
        json={"regions": [{"name": "region-1", "id": "r1", "status": "available"}]},
    )
    httpx_mock.add_response(
        method="GET",
        url=httpx.URL(f"{vpc_base}/instances").copy_merge_params(
            {"version": "2024-01-01", "generation": "2"}
        ),
        json={"instances": [{"name": "vm-1", "id": "i1", "status": "running"}]},
    )
    httpx_mock.add_response(
        method="GET",
        url=httpx.URL(f"{vpc_base}/vpcs").copy_merge_params(
            {"version": "2024-01-01", "generation": "2"}
        ),
        json={"vpcs": [{"name": "vpc-1", "id": "v1"}]},
    )
    httpx_mock.add_response(
        method="GET",
        url=httpx.URL(f"{vpc_base}/subnets").copy_merge_params(
            {"version": "2024-01-01", "generation": "2"}
        ),
        json={"subnets": [{"name": "subnet-1", "id": "s1"}]},
    )
    httpx_mock.add_response(
        method="GET",
        url=httpx.URL(f"{vpc_base}/security_groups").copy_merge_params(
            {"version": "2024-01-01", "generation": "2"}
        ),
        json={"security_groups": [{"name": "sg-1", "id": "sg1"}]},
    )
    httpx_mock.add_response(
        method="GET",
        url=httpx.URL(f"{vpc_base}/load_balancers").copy_merge_params(
            {"version": "2024-01-01", "generation": "2"}
        ),
        json={"load_balancers": [{"name": "lb-1", "id": "lb1"}]},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://resource-controller.cloud.ibm.com/v2/resource_instances",
        json={"resources": [{"name": "storage-1", "id": "res1", "resource_plan_id": "plan1"}]},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://containers.cloud.ibm.com/global/v1/clusters",
        json=[{"name": "iks-1"}],
    )

    resources = await IbmProvider().enumerate(
        "acct", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
    )
    names = {resource.name for resource in resources}
    assert names == {
        "region-1",
        "vm-1",
        "vpc-1",
        "subnet-1",
        "sg-1",
        "lb-1",
        "storage-1",
        "iks-1",
    }
    instance = next(r for r in resources if r.name == "vm-1")
    assert instance.identity["status"] == "running"


async def test_enumerate_token_endpoint_unreachable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with pytest.raises(EnumerationError, match="IAM token endpoint unreachable"):
        await IbmProvider().enumerate(
            "acct", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_token_request_denied(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_IAM_TOKEN_URL, status_code=401)
    with pytest.raises(EnumerationError, match="IBM Cloud authentication failed"):
        await IbmProvider().enumerate(
            "acct", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_token_response_missing_access_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_IAM_TOKEN_URL, json={})
    with pytest.raises(EnumerationError, match="did not contain an access_token"):
        await IbmProvider().enumerate(
            "acct", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_vpc_401_raises_enumeration_error(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    httpx_mock.add_response(method="GET", status_code=401)
    with pytest.raises(EnumerationError, match="IBM Cloud authorization failed"):
        await IbmProvider().enumerate(
            "acct", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_vpc_non_200_returns_empty_for_that_resource(
    httpx_mock: HTTPXMock,
) -> None:
    _mock_token(httpx_mock)
    for _ in range(6):
        httpx_mock.add_response(method="GET", status_code=404)
    httpx_mock.add_response(
        method="GET",
        url="https://resource-controller.cloud.ibm.com/v2/resource_instances",
        json={"resources": []},
    )
    httpx_mock.add_response(
        method="GET", url="https://containers.cloud.ibm.com/global/v1/clusters", json=[]
    )
    resources = await IbmProvider().enumerate(
        "acct", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
    )
    assert resources == []


async def test_enumerate_resource_controller_401_raises_enumeration_error(
    httpx_mock: HTTPXMock,
) -> None:
    _mock_token(httpx_mock)
    for _ in range(6):
        httpx_mock.add_response(method="GET", status_code=404)
    httpx_mock.add_response(
        method="GET",
        url="https://resource-controller.cloud.ibm.com/v2/resource_instances",
        status_code=401,
    )
    with pytest.raises(EnumerationError, match="Resource Controller"):
        await IbmProvider().enumerate(
            "acct", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_kubernetes_service_401_raises_enumeration_error(
    httpx_mock: HTTPXMock,
) -> None:
    _mock_token(httpx_mock)
    for _ in range(6):
        httpx_mock.add_response(method="GET", status_code=404)
    httpx_mock.add_response(
        method="GET",
        url="https://resource-controller.cloud.ibm.com/v2/resource_instances",
        json={"resources": []},
    )
    httpx_mock.add_response(
        method="GET", url="https://containers.cloud.ibm.com/global/v1/clusters", status_code=403
    )
    with pytest.raises(EnumerationError, match="Kubernetes Service"):
        await IbmProvider().enumerate(
            "acct", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_vpc_request_unreachable(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with pytest.raises(EnumerationError, match="IBM VPC request"):
        await IbmProvider().enumerate(
            "acct", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_resource_controller_unreachable(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    for _ in range(6):
        httpx_mock.add_response(method="GET", status_code=404)
    httpx_mock.add_exception(
        httpx.ConnectError("refused"),
        url="https://resource-controller.cloud.ibm.com/v2/resource_instances",
    )
    with pytest.raises(EnumerationError, match="IBM Resource Controller unreachable"):
        await IbmProvider().enumerate(
            "acct", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_kubernetes_service_unreachable(httpx_mock: HTTPXMock) -> None:
    _mock_token(httpx_mock)
    for _ in range(6):
        httpx_mock.add_response(method="GET", status_code=404)
    httpx_mock.add_response(
        method="GET",
        url="https://resource-controller.cloud.ibm.com/v2/resource_instances",
        json={"resources": []},
    )
    httpx_mock.add_exception(
        httpx.ConnectError("refused"), url="https://containers.cloud.ibm.com/global/v1/clusters"
    )
    with pytest.raises(EnumerationError, match="IBM Kubernetes Service unreachable"):
        await IbmProvider().enumerate(
            "acct", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )
