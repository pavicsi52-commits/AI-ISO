"""Token store ("TOKEN MANAGEMENT": OAuth, Access, Refresh, Webhook,
Cloud, AI Tokens). No REST surface -- docs/035's own REST list omits
``/tokens`` entirely, unlike certificates/ssh-keys/api-keys/providers --
so this exists for programmatic completeness/internal use only, the
same "required table, no REST list entry" shape
``services/project-service``'s no-REST-surface sub-resources share.

The token value itself is stored as a
:class:`~app.models.secret.Secret`, referenced by :attr:`secret_id` --
callers create that secret first (via
:class:`~app.services.secret.SecretService`), then register it here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import TokenStatus, TokenType
from app.models.token import TokenEntry
from app.repositories.token import TokenRepository


class TokenService:
    """Registers and manages the lifecycle of tokens referencing the vault."""

    def __init__(self, tokens: TokenRepository) -> None:
        self._tokens = tokens

    async def list_for_org(self, organization_id: UUID) -> list[TokenEntry]:
        """Every managed token belonging to *organization_id*."""
        return await self._tokens.list_for_org(organization_id)

    async def register(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        token_type: TokenType,
        secret_id: UUID,
        expires_at: datetime | None = None,
    ) -> TokenEntry:
        """Register a new token referencing an already-created secret."""
        return await self._tokens.create(
            TokenEntry(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                token_type=token_type,
                secret_id=secret_id,
                expires_at=expires_at,
            )
        )

    async def revoke(self, token_id: UUID) -> TokenEntry:
        """Mark a token revoked.

        Raises:
            NotFoundError: If no such token exists.
        """
        token = await self._tokens.require_by_id(token_id)
        token.status = TokenStatus.REVOKED
        return token

    async def mark_expired_if_due(self, token: TokenEntry, *, now: datetime | None = None) -> None:
        """Mark *token* expired if it has passed :attr:`~TokenEntry.expires_at`."""
        current = now or datetime.now(UTC)
        if token.expires_at is not None and token.expires_at <= current:
            token.status = TokenStatus.EXPIRED


__all__ = ["TokenService"]
