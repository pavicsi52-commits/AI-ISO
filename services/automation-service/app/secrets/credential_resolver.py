"""Live credential resolution against the Secrets Management Service.

Per docs/040 "SECRETS MANAGEMENT" "Support": Credential Injection, SSH
Keys, Certificates, API Keys, Vault References, Temporary Credentials.
"Secrets SHALL never be logged." :attr:`~app.models.automation_target
.AutomationTarget.credential_ref` stores only a reference id --
resolving the real credential value always means a live
``GET /secrets/{id}`` call to ``services/secrets-management-service``,
forwarding the calling user's own Bearer token so that service's own
ACL (owner or explicit grant) applies exactly as it would for any
other caller. The resolved value is held only in memory for the
duration of one execution and is never written to any table, the same
"resolve live, never persist plaintext" precedent
``services/discovery-service``'s own ``CredentialResolver`` and
``services/configuration-management-service``'s own
``GitCredentialResolver`` established.
"""

from __future__ import annotations

import httpx
from shared_core.exceptions.dependency import DependencyError


class SecretCredentialResolver:
    """Resolves an ``credential_ref`` id into its real value."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def resolve(self, secret_id: str, *, caller_token: str) -> str:
        """Fetch *secret_id*'s real value from the Secrets Management Service.

        Raises:
            DependencyError: If the Secrets Management Service is
                unreachable, denies access, or has no such secret.
        """
        url = f"{self._base_url}/secrets/{secret_id}"
        headers = {"Authorization": f"Bearer {caller_token}"}
        try:
            response = await self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise DependencyError(f"Secrets Management Service unreachable: {exc}") from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            raise DependencyError(f"Secret '{secret_id}' was not found.")
        if response.status_code in (401, 403):
            raise DependencyError(f"Not authorized to read secret '{secret_id}'.")
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Secrets Management Service returned HTTP {response.status_code}."
            )
        return str(response.json()["data"]["value"])


__all__ = ["SecretCredentialResolver"]
