"""Google Cloud discovery, via direct REST calls to the real Compute
Engine, Cloud Storage, Cloud SQL, and GKE APIs.

Per docs/037 "CLOUD DISCOVERY". Uses ``httpx`` plus a hand-built
service-account JWT-bearer OAuth2 exchange (RFC 7523, signed with
``cryptography`` -- already a dependency via ``paramiko``) rather than
the full ``google-cloud-*`` SDK family, for the same "real REST
contract, leaner dependency footprint" reasoning as
``azure_provider.py``.

**Not verified against a real GCP project in this environment.**
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt as pyjwt

from app.models.enums import TargetType
from app.scanners.base import ScanCredential
from app.scanners.enumeration import DiscoveredResource, EnumerationError, EnumerationProvider

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_COMPUTE_BASE = "https://compute.googleapis.com/compute/v1"


class GcpProvider(EnumerationProvider):
    """Enumerates a GCP project's zones, instances, networking, storage,
    Cloud SQL instances, and GKE clusters.
    """

    target_type = TargetType.CLOUD_ACCOUNT

    async def enumerate(
        self, address: str, *, credential: ScanCredential | None, timeout_seconds: float
    ) -> list[DiscoveredResource]:
        if credential is None:
            raise EnumerationError("GCP requires a service-account credential.")
        project_id = credential.extra.get("project_id")
        client_email = credential.extra.get("client_email")
        private_key = credential.private_key
        if not project_id or not client_email or not private_key:
            raise EnumerationError(
                "GCP requires 'project_id'/'client_email' in credential.extra and a private_key."
            )

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            token = await self._acquire_token(client, str(client_email), private_key)
            headers = {"Authorization": f"Bearer {token}"}

            resources: list[DiscoveredResource] = []
            resources += await self._list_zones(client, str(project_id), headers)
            resources += await self._list_aggregated(
                client, str(project_id), "instances", "instance", headers
            )
            resources += await self._list_aggregated(
                client, str(project_id), "subnetworks", "subnet", headers
            )
            resources += await self._list_aggregated(
                client, str(project_id), "firewalls", "security_group", headers
            )
            resources += await self._list_aggregated(
                client, str(project_id), "forwardingRules", "load_balancer", headers
            )
            resources += await self._list_networks(client, str(project_id), headers)
            resources += await self._list_buckets(client, str(project_id), headers)
            resources += await self._list_sql_instances(client, str(project_id), headers)
            resources += await self._list_gke_clusters(client, str(project_id), headers)
            return resources

    async def _acquire_token(
        self, client: httpx.AsyncClient, client_email: str, private_key: str
    ) -> str:
        now = int(time.time())
        assertion = pyjwt.encode(
            {
                "iss": client_email,
                "scope": _SCOPE,
                "aud": _TOKEN_URI,
                "iat": now,
                "exp": now + 3600,
            },
            private_key,
            algorithm="RS256",
        )
        try:
            response = await client.post(
                _TOKEN_URI,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
        except httpx.HTTPError as exc:
            raise EnumerationError(f"Google token endpoint unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise EnumerationError(f"GCP authentication failed: HTTP {response.status_code}")
        token = response.json().get("access_token")
        if not token:
            raise EnumerationError("Google token response did not contain an access_token.")
        return str(token)

    async def _get(
        self, client: httpx.AsyncClient, url: str, headers: dict[str, str]
    ) -> dict[str, Any]:
        try:
            response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise EnumerationError(f"GCP request to {url!r} failed: {exc}") from exc
        if response.status_code in (401, 403):
            raise EnumerationError(
                f"GCP authorization failed for {url!r}: HTTP {response.status_code}"
            )
        if response.status_code != httpx.codes.OK:
            return {}
        result: dict[str, Any] = response.json()
        return result

    async def _list_zones(
        self, client: httpx.AsyncClient, project_id: str, headers: dict[str, str]
    ) -> list[DiscoveredResource]:
        body = await self._get(client, f"{_COMPUTE_BASE}/projects/{project_id}/zones", headers)
        return [
            DiscoveredResource(name=item["name"], resource_type="availability_zone")
            for item in body.get("items", [])
        ]

    async def _list_aggregated(
        self,
        client: httpx.AsyncClient,
        project_id: str,
        collection: str,
        resource_type: str,
        headers: dict[str, str],
    ) -> list[DiscoveredResource]:
        body = await self._get(
            client, f"{_COMPUTE_BASE}/projects/{project_id}/aggregated/{collection}", headers
        )
        resources: list[DiscoveredResource] = []
        for scope in body.get("items", {}).values():
            for item in scope.get(collection, []):
                resources.append(
                    DiscoveredResource(
                        name=item["name"],
                        resource_type=resource_type,
                        identity={"id": item.get("id")},
                    )
                )
        return resources

    async def _list_networks(
        self, client: httpx.AsyncClient, project_id: str, headers: dict[str, str]
    ) -> list[DiscoveredResource]:
        body = await self._get(
            client, f"{_COMPUTE_BASE}/projects/{project_id}/global/networks", headers
        )
        return [
            DiscoveredResource(name=item["name"], resource_type="virtual_network")
            for item in body.get("items", [])
        ]

    async def _list_buckets(
        self, client: httpx.AsyncClient, project_id: str, headers: dict[str, str]
    ) -> list[DiscoveredResource]:
        body = await self._get(
            client, f"https://storage.googleapis.com/storage/v1/b?project={project_id}", headers
        )
        return [
            DiscoveredResource(name=item["name"], resource_type="storage")
            for item in body.get("items", [])
        ]

    async def _list_sql_instances(
        self, client: httpx.AsyncClient, project_id: str, headers: dict[str, str]
    ) -> list[DiscoveredResource]:
        body = await self._get(
            client,
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{project_id}/instances",
            headers,
        )
        return [
            DiscoveredResource(
                name=item["name"],
                resource_type="managed_database",
                identity={"database_version": item.get("databaseVersion")},
            )
            for item in body.get("items", [])
        ]

    async def _list_gke_clusters(
        self, client: httpx.AsyncClient, project_id: str, headers: dict[str, str]
    ) -> list[DiscoveredResource]:
        body = await self._get(
            client,
            f"https://container.googleapis.com/v1/projects/{project_id}/locations/-/clusters",
            headers,
        )
        return [
            DiscoveredResource(name=item["name"], resource_type="kubernetes_service")
            for item in body.get("clusters", [])
        ]


__all__ = ["GcpProvider"]
