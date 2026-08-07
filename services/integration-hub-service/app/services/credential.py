"""Connector credential management (docs/058 "CREDENTIAL MANAGEMENT")."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.connectors.credentials import CredentialType
from shared_core.exceptions.validation import ValidationError
from shared_core.security.encryption import decrypt, encrypt

from app.models.credential import ConnectorCredential
from app.models.enums import CredentialStatus
from app.repositories.credential import ConnectorCredentialRepository
from app.security.credential_resolver import SecretCredentialResolver


class CredentialService:
    """Assigns, rotates, and resolves one connector's own credential material.

    Exactly one of *secret_ref* (a secrets-management-service reference,
    resolved live) or *raw_value* (encrypted here, for a self-managed
    OAuth2 token this service's own token exchange obtained) is ever
    given to :meth:`assign` -- see ``ConnectorCredential``'s own
    docstring for why.
    """

    def __init__(
        self,
        credentials: ConnectorCredentialRepository,
        *,
        encryption_key: str,
        resolver: SecretCredentialResolver | None = None,
    ) -> None:
        self._credentials = credentials
        self._encryption_key = encryption_key
        self._resolver = resolver

    async def assign(
        self,
        organization_id: UUID,
        *,
        connector_id: UUID,
        credential_type: CredentialType,
        secret_ref: str | None = None,
        raw_value: str | None = None,
        refresh_value: str | None = None,
        expires_at: datetime | None = None,
        owner_id: str | None = None,
    ) -> ConnectorCredential:
        """Assign a credential to a connector.

        Raises:
            ValidationError: If neither, or both, of *secret_ref*/
                *raw_value* are given.
        """
        if bool(secret_ref) == bool(raw_value):
            raise ValidationError("Exactly one of secret_ref or raw_value must be given.")
        return await self._credentials.create(
            ConnectorCredential(
                organization_id=organization_id,
                connector_id=connector_id,
                credential_type=credential_type,
                secret_ref=secret_ref,
                encrypted_value=encrypt(raw_value, key=self._encryption_key) if raw_value else None,
                encrypted_refresh_value=(
                    encrypt(refresh_value, key=self._encryption_key) if refresh_value else None
                ),
                expires_at=expires_at,
                owner_id=owner_id,
                status=CredentialStatus.ACTIVE,
            )
        )

    async def get(self, organization_id: UUID, credential_id: UUID) -> ConnectorCredential:
        """One credential.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._credentials.require_in_org(organization_id, credential_id)

    async def list_for_connector(self, connector_id: UUID) -> list[ConnectorCredential]:
        """Every credential ever assigned to one connector, newest first."""
        return await self._credentials.list_for_connector(connector_id)

    async def get_active_for_connector(self, connector_id: UUID) -> ConnectorCredential | None:
        """The credential a connector actually authenticates with right now, if any."""
        return await self._credentials.get_active_for_connector(connector_id)

    async def rotate(
        self,
        organization_id: UUID,
        credential_id: UUID,
        *,
        raw_value: str,
        refresh_value: str | None = None,
        expires_at: datetime | None = None,
    ) -> ConnectorCredential:
        """Replace a self-managed credential's own encrypted value.

        *expires_at*, like *refresh_value*, is left untouched when not
        given -- a caller rotating a credential's value without knowing
        its new expiry must not silently erase the previous one, which
        would otherwise drop that credential out of
        :meth:`list_expiring_before`'s own sweep forever.
        """
        credential = await self.get(organization_id, credential_id)
        credential.encrypted_value = encrypt(raw_value, key=self._encryption_key)
        if refresh_value is not None:
            credential.encrypted_refresh_value = encrypt(refresh_value, key=self._encryption_key)
        if expires_at is not None:
            credential.expires_at = expires_at
        credential.last_rotated_at = datetime.now(UTC)
        credential.status = CredentialStatus.ACTIVE
        return await self._credentials.update(credential)

    async def resolve_value(
        self, credential: ConnectorCredential, *, caller_token: str = ""
    ) -> str:
        """The credential's own real, usable value.

        Raises:
            DependencyError: If *credential* references a
                secrets-management-service secret and that service is
                unreachable, denies access, or has no such secret.
            ValidationError: If *credential* has neither a reference nor
                a self-managed value (a data integrity issue, never
                reachable through :meth:`assign`'s own validation).
        """
        if credential.encrypted_value is not None:
            return decrypt(credential.encrypted_value, key=self._encryption_key)
        if credential.secret_ref is not None:
            if self._resolver is None:
                raise ValidationError(
                    "This credential references an external secret but no resolver is configured."
                )
            return await self._resolver.resolve(credential.secret_ref, caller_token=caller_token)
        raise ValidationError("This credential has no resolvable value.")

    async def resolve_refresh_value(self, credential: ConnectorCredential) -> str | None:
        """The credential's own self-managed refresh token, if any."""
        if credential.encrypted_refresh_value is None:
            return None
        return decrypt(credential.encrypted_refresh_value, key=self._encryption_key)

    async def mark_expired(self, credential: ConnectorCredential) -> ConnectorCredential:
        """Mark one credential expired -- called by the expiry sweep."""
        credential.status = CredentialStatus.EXPIRED
        return await self._credentials.update(credential)

    async def list_expiring_before(
        self, cutoff: datetime, *, limit: int = 500
    ) -> list[ConnectorCredential]:
        """Active credentials past *cutoff* -- for the expiry sweep."""
        return await self._credentials.list_expiring_before(cutoff, limit=limit)


__all__ = ["CredentialService"]
