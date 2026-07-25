"""IBM Cloud discovery, via direct REST calls to the real VPC, Resource
Controller, and Kubernetes Service APIs.

Per docs/037 "CLOUD DISCOVERY". Uses ``httpx`` plus IBM Cloud's real
IAM API-key token exchange rather than the ``ibm-cloud-sdk-core``/
``ibm-vpc`` SDKs, for the same "real REST contract, leaner dependency
footprint" reasoning as ``azure_provider.py``/``gcp_provider.py``/
``oracle_provider.py``.

**Not verified against a real IBM Cloud account in this environment.**
"""

from __future__ import annotations

import httpx

from app.models.enums import TargetType
from app.scanners.base import ScanCredential
from app.scanners.enumeration import DiscoveredResource, EnumerationError, EnumerationProvider

_IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
_VPC_API_VERSION = "2024-01-01"
_VPC_GENERATION = "2"


class IbmProvider(EnumerationProvider):
    """Enumerates an IBM Cloud account's regions, VPC instances/networking,
    resource-controller-managed storage/databases, and Kubernetes Service clusters.
    """

    target_type = TargetType.CLOUD_ACCOUNT

    async def enumerate(
        self, address: str, *, credential: ScanCredential | None, timeout_seconds: float
    ) -> list[DiscoveredResource]:
        if credential is None or not credential.token:
            raise EnumerationError("IBM Cloud requires an API key credential (in 'token').")
        region = (credential.extra.get("region") if credential else None) or "us-south"

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            access_token = await self._acquire_token(client, credential.token)
            headers = {"Authorization": f"Bearer {access_token}"}
            vpc_base = f"https://{region}.iaas.cloud.ibm.com/v1"
            vpc_params = {"version": _VPC_API_VERSION, "generation": _VPC_GENERATION}

            resources: list[DiscoveredResource] = []
            resources += await self._list_vpc(
                client, f"{vpc_base}/regions", vpc_params, headers, "region", "regions"
            )
            resources += await self._list_vpc(
                client, f"{vpc_base}/instances", vpc_params, headers, "instance", "instances"
            )
            resources += await self._list_vpc(
                client, f"{vpc_base}/vpcs", vpc_params, headers, "virtual_network", "vpcs"
            )
            resources += await self._list_vpc(
                client, f"{vpc_base}/subnets", vpc_params, headers, "subnet", "subnets"
            )
            resources += await self._list_vpc(
                client,
                f"{vpc_base}/security_groups",
                vpc_params,
                headers,
                "security_group",
                "security_groups",
            )
            resources += await self._list_vpc(
                client,
                f"{vpc_base}/load_balancers",
                vpc_params,
                headers,
                "load_balancer",
                "load_balancers",
            )
            resources += await self._list_resource_instances(client, headers)
            resources += await self._list_kubernetes_clusters(client, headers)
            return resources

    async def _acquire_token(self, client: httpx.AsyncClient, api_key: str) -> str:
        try:
            response = await client.post(
                _IAM_TOKEN_URL,
                data={
                    "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                    "apikey": api_key,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise EnumerationError(f"IBM IAM token endpoint unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise EnumerationError(f"IBM Cloud authentication failed: HTTP {response.status_code}")
        token = response.json().get("access_token")
        if not token:
            raise EnumerationError("IBM IAM token response did not contain an access_token.")
        return str(token)

    async def _list_vpc(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, str],
        headers: dict[str, str],
        resource_type: str,
        body_key: str,
    ) -> list[DiscoveredResource]:
        try:
            response = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise EnumerationError(f"IBM VPC request to {url!r} failed: {exc}") from exc
        if response.status_code in (401, 403):
            raise EnumerationError(
                f"IBM Cloud authorization failed for {url!r}: HTTP {response.status_code}"
            )
        if response.status_code != httpx.codes.OK:
            return []
        body = response.json()
        return [
            DiscoveredResource(
                name=item.get("name", item.get("id", "unknown")),
                resource_type=resource_type,
                identity={"id": item.get("id"), "status": item.get("status")},
            )
            for item in body.get(body_key, [])
        ]

    async def _list_resource_instances(
        self, client: httpx.AsyncClient, headers: dict[str, str]
    ) -> list[DiscoveredResource]:
        try:
            response = await client.get(
                "https://resource-controller.cloud.ibm.com/v2/resource_instances", headers=headers
            )
        except httpx.HTTPError as exc:
            raise EnumerationError(f"IBM Resource Controller unreachable: {exc}") from exc
        if response.status_code in (401, 403):
            raise EnumerationError(
                f"IBM Cloud authorization failed for the Resource Controller: "
                f"HTTP {response.status_code}"
            )
        if response.status_code != httpx.codes.OK:
            return []
        return [
            DiscoveredResource(
                name=item.get("name", "unknown"),
                resource_type="storage",
                identity={"id": item.get("id"), "resource_plan_id": item.get("resource_plan_id")},
            )
            for item in response.json().get("resources", [])
        ]

    async def _list_kubernetes_clusters(
        self, client: httpx.AsyncClient, headers: dict[str, str]
    ) -> list[DiscoveredResource]:
        try:
            response = await client.get(
                "https://containers.cloud.ibm.com/global/v1/clusters", headers=headers
            )
        except httpx.HTTPError as exc:
            raise EnumerationError(f"IBM Kubernetes Service unreachable: {exc}") from exc
        if response.status_code in (401, 403):
            raise EnumerationError(
                f"IBM Cloud authorization failed for Kubernetes Service: "
                f"HTTP {response.status_code}"
            )
        if response.status_code != httpx.codes.OK:
            return []
        return [
            DiscoveredResource(name=item.get("name", "unknown"), resource_type="kubernetes_service")
            for item in response.json()
        ]


__all__ = ["IbmProvider"]
