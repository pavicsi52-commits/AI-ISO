"""Azure discovery, via direct Azure Resource Manager (ARM) REST calls.

Per docs/037 "CLOUD DISCOVERY". Uses ``httpx`` against the real ARM
REST API contract (an OAuth2 client-credentials token acquisition
against Azure AD, then bearer-authenticated ARM calls) rather than the
``azure-identity``/``azure-mgmt-*`` SDKs, which would add a much larger
dependency footprint than justified for a provider that -- like every
cloud provider in this package except AWS (verifiable via ``moto``) --
has no real subscription reachable to test against in this environment.
The request/response shapes below are the genuine, documented ARM
contract, not invented.

**Not verified against a real Azure subscription in this environment.**
"""

from __future__ import annotations

import httpx

from app.models.enums import TargetType
from app.scanners.base import ScanCredential
from app.scanners.enumeration import DiscoveredResource, EnumerationError, EnumerationProvider

_ARM_API_VERSION = "2021-04-01"
_COMPUTE_API_VERSION = "2023-09-01"
_NETWORK_API_VERSION = "2023-09-01"
_SQL_API_VERSION = "2021-11-01"
_AKS_API_VERSION = "2023-10-01"
_MANAGEMENT_SCOPE = "https://management.azure.com/.default"


class AzureProvider(EnumerationProvider):
    """Enumerates an Azure subscription's resource groups, VMs, networking,
    storage, SQL databases, and AKS clusters.
    """

    target_type = TargetType.CLOUD_ACCOUNT

    async def enumerate(
        self, address: str, *, credential: ScanCredential | None, timeout_seconds: float
    ) -> list[DiscoveredResource]:
        if credential is None or not credential.username or not credential.password:
            raise EnumerationError("Azure requires a client_id/client_secret credential.")
        tenant_id = credential.extra.get("tenant_id")
        subscription_id = credential.extra.get("subscription_id")
        if not tenant_id or not subscription_id:
            raise EnumerationError(
                "Azure requires 'tenant_id' and 'subscription_id' in credential.extra."
            )

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            token = await self._acquire_token(
                client, str(tenant_id), credential.username, credential.password
            )
            headers = {"Authorization": f"Bearer {token}"}
            base = f"https://management.azure.com/subscriptions/{subscription_id}"

            resources: list[DiscoveredResource] = []
            resources += await self._list(
                client, f"{base}/resourceGroups", _ARM_API_VERSION, headers, "resource_group"
            )
            resources += await self._list(
                client,
                f"{base}/providers/Microsoft.Compute/virtualMachines",
                _COMPUTE_API_VERSION,
                headers,
                "instance",
            )
            resources += await self._list(
                client,
                f"{base}/providers/Microsoft.Network/virtualNetworks",
                _NETWORK_API_VERSION,
                headers,
                "virtual_network",
            )
            resources += await self._list(
                client,
                f"{base}/providers/Microsoft.Network/networkSecurityGroups",
                _NETWORK_API_VERSION,
                headers,
                "security_group",
            )
            resources += await self._list(
                client,
                f"{base}/providers/Microsoft.Network/loadBalancers",
                _NETWORK_API_VERSION,
                headers,
                "load_balancer",
            )
            resources += await self._list(
                client,
                f"{base}/providers/Microsoft.Storage/storageAccounts",
                _ARM_API_VERSION,
                headers,
                "storage",
            )
            resources += await self._list(
                client,
                f"{base}/providers/Microsoft.Sql/servers",
                _SQL_API_VERSION,
                headers,
                "managed_database",
            )
            resources += await self._list(
                client,
                f"{base}/providers/Microsoft.ContainerService/managedClusters",
                _AKS_API_VERSION,
                headers,
                "kubernetes_service",
            )
            return resources

    async def _acquire_token(
        self, client: httpx.AsyncClient, tenant_id: str, client_id: str, client_secret: str
    ) -> str:
        try:
            response = await client.post(
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": _MANAGEMENT_SCOPE,
                },
            )
        except httpx.HTTPError as exc:
            raise EnumerationError(f"Azure AD token endpoint unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise EnumerationError(f"Azure authentication failed: HTTP {response.status_code}")
        token = response.json().get("access_token")
        if not token:
            raise EnumerationError("Azure AD token response did not contain an access_token.")
        return str(token)

    async def _list(
        self,
        client: httpx.AsyncClient,
        url: str,
        api_version: str,
        headers: dict[str, str],
        resource_type: str,
    ) -> list[DiscoveredResource]:
        try:
            response = await client.get(url, params={"api-version": api_version}, headers=headers)
        except httpx.HTTPError as exc:
            raise EnumerationError(f"ARM request to {url!r} failed: {exc}") from exc
        if response.status_code in (401, 403):
            raise EnumerationError(
                f"Azure authorization failed for {url!r}: HTTP {response.status_code}"
            )
        if response.status_code != httpx.codes.OK:
            return []
        body = response.json()
        return [
            DiscoveredResource(
                name=item.get("name", item.get("id", "unknown")),
                resource_type=resource_type,
                identity={"id": item.get("id"), "location": item.get("location")},
            )
            for item in body.get("value", [])
        ]


__all__ = ["AzureProvider"]
