"""Oracle Cloud Infrastructure (OCI) discovery, via direct signed REST calls.

Per docs/037 "CLOUD DISCOVERY". OCI authenticates every API request
with an RSA-SHA256 request signature (not a bearer token) -- this
module implements that real signing algorithm directly with
``cryptography`` (the same "real REST contract, no heavy vendor SDK"
choice ``azure_provider.py``/``gcp_provider.py`` make, here because the
official ``oci`` SDK is a very large dependency for a provider that
can never be exercised live in this environment anyway) rather than
adding the official ``oci`` SDK.

**Not verified against a real OCI tenancy in this environment.**
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from email.utils import format_datetime

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.models.enums import TargetType
from app.scanners.base import ScanCredential
from app.scanners.enumeration import DiscoveredResource, EnumerationError, EnumerationProvider

_API_VERSION = "20160918"


def _sign_request(
    *, method: str, path: str, host: str, key_id: str, private_key_pem: str
) -> dict[str, str]:
    """Build the real OCI request-signature headers for one GET request."""
    date_header = format_datetime(datetime.now(UTC), usegmt=True)
    signing_string = f"(request-target): {method.lower()} {path}\ndate: {date_header}\nhost: {host}"

    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    if not isinstance(private_key, RSAPrivateKey):
        raise EnumerationError("OCI private key must be an RSA key.")
    signature = private_key.sign(signing_string.encode(), padding.PKCS1v15(), hashes.SHA256())
    signature_b64 = base64.b64encode(signature).decode()

    authorization = (
        f'Signature version="1",keyId="{key_id}",algorithm="rsa-sha256",'
        f'headers="(request-target) date host",signature="{signature_b64}"'
    )
    return {"Date": date_header, "Host": host, "Authorization": authorization}


class OracleProvider(EnumerationProvider):
    """Enumerates an OCI tenancy's compartments, compute, networking,
    storage, autonomous databases, and OKE clusters.
    """

    target_type = TargetType.CLOUD_ACCOUNT

    async def enumerate(
        self, address: str, *, credential: ScanCredential | None, timeout_seconds: float
    ) -> list[DiscoveredResource]:
        if credential is None or not credential.username or not credential.private_key:
            raise EnumerationError("OCI requires a user OCID (username) and an RSA private_key.")
        tenancy_ocid = credential.extra.get("tenancy_ocid")
        fingerprint = credential.extra.get("key_fingerprint")
        compartment_id = credential.extra.get("compartment_id") or tenancy_ocid
        region = credential.extra.get("region") or "us-ashburn-1"
        if not tenancy_ocid or not fingerprint:
            raise EnumerationError(
                "OCI requires 'tenancy_ocid' and 'key_fingerprint' in credential.extra."
            )

        key_id = f"{tenancy_ocid}/{credential.username}/{fingerprint}"
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resources: list[DiscoveredResource] = []
            resources += await self._list(
                client,
                f"identity.{region}.oraclecloud.com",
                f"/{_API_VERSION}/regions",
                {},
                "region",
                key_id,
                credential.private_key,
            )
            resources += await self._list(
                client,
                f"iaas.{region}.oraclecloud.com",
                f"/{_API_VERSION}/instances",
                {"compartmentId": str(compartment_id)},
                "instance",
                key_id,
                credential.private_key,
            )
            resources += await self._list(
                client,
                f"iaas.{region}.oraclecloud.com",
                f"/{_API_VERSION}/vcns",
                {"compartmentId": str(compartment_id)},
                "virtual_network",
                key_id,
                credential.private_key,
            )
            resources += await self._list(
                client,
                f"iaas.{region}.oraclecloud.com",
                f"/{_API_VERSION}/subnets",
                {"compartmentId": str(compartment_id)},
                "subnet",
                key_id,
                credential.private_key,
            )
            resources += await self._list(
                client,
                f"iaas.{region}.oraclecloud.com",
                f"/{_API_VERSION}/securityLists",
                {"compartmentId": str(compartment_id)},
                "security_group",
                key_id,
                credential.private_key,
            )
            resources += await self._list(
                client,
                f"loadbalancer.{region}.oraclecloud.com",
                "/20170115/loadBalancers",
                {"compartmentId": str(compartment_id)},
                "load_balancer",
                key_id,
                credential.private_key,
            )
            resources += await self._list(
                client,
                f"database.{region}.oraclecloud.com",
                f"/{_API_VERSION}/autonomousDatabases",
                {"compartmentId": str(compartment_id)},
                "managed_database",
                key_id,
                credential.private_key,
            )
            resources += await self._list(
                client,
                f"containerengine.{region}.oraclecloud.com",
                "/20180222/clusters",
                {"compartmentId": str(compartment_id)},
                "kubernetes_service",
                key_id,
                credential.private_key,
            )
            return resources

    async def _list(
        self,
        client: httpx.AsyncClient,
        host: str,
        path: str,
        query: dict[str, str],
        resource_type: str,
        key_id: str,
        private_key_pem: str,
    ) -> list[DiscoveredResource]:
        headers = _sign_request(
            method="get", path=path, host=host, key_id=key_id, private_key_pem=private_key_pem
        )
        try:
            response = await client.get(f"https://{host}{path}", params=query, headers=headers)
        except httpx.HTTPError as exc:
            raise EnumerationError(f"OCI request to {host}{path} failed: {exc}") from exc
        if response.status_code in (401, 403):
            raise EnumerationError(
                f"OCI authorization failed for {host}{path}: HTTP {response.status_code}"
            )
        if response.status_code != httpx.codes.OK:
            return []
        body = response.json()
        items = body if isinstance(body, list) else body.get("items", [])
        return [
            DiscoveredResource(
                name=item.get("displayName") or item.get("name") or item.get("id", "unknown"),
                resource_type=resource_type,
                identity={"id": item.get("id"), "lifecycle_state": item.get("lifecycleState")},
            )
            for item in items
        ]


__all__ = ["OracleProvider"]
