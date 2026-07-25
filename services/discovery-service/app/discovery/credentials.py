"""Live credential resolution against the Secrets Management Service.

Per docs/037 "SECURITY": "Credentials must be retrieved only from the
Secrets Management Service. Never persist plaintext credentials."
:class:`DiscoveryCredential` stores only a reference
(:attr:`~app.models.discovery_credential.DiscoveryCredential.secret_id`)
-- resolving the actual value always means a live
``GET /secrets/{id}`` call to ``services/secrets-management-service``
(the one endpoint on that service that returns a decrypted value, per
its own README), forwarding the calling user's own Bearer token so
that service's own ACL (owner or explicit grant) applies exactly as it
would for any other caller. The resolved :class:`~app.scanners.base
.ScanCredential` is held only in memory for the duration of one probe
and is never written to any table.
"""

from __future__ import annotations

import httpx
from shared_core.exceptions.dependency import DependencyError

from app.models.discovery_credential import DiscoveryCredential
from app.models.enums import CredentialType
from app.scanners.base import ScanCredential


class CredentialResolver:
    """Resolves a :class:`DiscoveryCredential` reference into real
    credential material, live, on every call.
    """

    def __init__(self, client: httpx.AsyncClient, *, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def resolve(
        self, credential: DiscoveryCredential, *, caller_token: str
    ) -> ScanCredential:
        """Fetch and shape *credential*'s real value from the Secrets
        Management Service.

        Raises:
            DependencyError: If the Secrets Management Service is
                unreachable, denies access, or has no such secret.
        """
        url = f"{self._base_url}/secrets/{credential.secret_id}"
        headers = {"Authorization": f"Bearer {caller_token}"}
        try:
            response = await self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise DependencyError(f"Secrets Management Service unreachable: {exc}") from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            raise DependencyError(f"Secret '{credential.secret_id}' was not found.")
        if response.status_code in (401, 403):
            raise DependencyError(f"Not authorized to read secret '{credential.secret_id}'.")
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Secrets Management Service returned HTTP {response.status_code}."
            )

        value = str(response.json()["data"]["value"])
        return _shape_credential(credential, value)


def _shape_credential(credential: DiscoveryCredential, value: str) -> ScanCredential:
    """Map one resolved secret value onto the field a given
    :class:`~app.models.enums.CredentialType` actually needs.
    """
    if credential.credential_type == CredentialType.SSH_KEY:
        return ScanCredential(username=credential.username, private_key=value)
    if credential.credential_type == CredentialType.PASSWORD:
        return ScanCredential(username=credential.username, password=value)
    if credential.credential_type in (CredentialType.API_KEY, CredentialType.TOKEN):
        return ScanCredential(username=credential.username, token=value)
    return ScanCredential(username=credential.username, extra={"certificate": value})


__all__ = ["CredentialResolver"]
