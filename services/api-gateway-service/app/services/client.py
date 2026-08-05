"""API client registration."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.client import ApiClient
from app.models.enums import ClientKind
from app.repositories.client import ApiClientRepository

_EDITABLE_FIELDS = frozenset(
    {
        "description",
        "contact_email",
        "default_rate_limit_id",
        "default_quota_id",
        "enabled",
    }
)


class ClientService:
    """Registered API consumers: registration and editing."""

    def __init__(self, clients: ApiClientRepository) -> None:
        self._clients = clients

    async def register(
        self,
        organization_id: UUID,
        *,
        name: str,
        client_kind: ClientKind = ClientKind.THIRD_PARTY,
        description: str | None = None,
        contact_email: str | None = None,
        actor_id: str | None = None,
    ) -> ApiClient:
        """Register a new API consumer."""
        return await self._clients.create(
            ApiClient(
                organization_id=organization_id,
                name=name,
                client_kind=client_kind,
                description=description,
                contact_email=contact_email,
                created_by=UUID(actor_id) if actor_id else None,
            )
        )

    async def get(self, organization_id: UUID, client_id: UUID) -> ApiClient:
        """One client.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._clients.require_in_org(organization_id, client_id)

    async def list_clients(self, organization_id: UUID) -> list[ApiClient]:
        """Every client registered in this organization."""
        return await self._clients.list_for_org(organization_id)

    async def update(
        self, organization_id: UUID, client_id: UUID, *, actor_id: str | None = None, **fields: Any
    ) -> ApiClient:
        """Edit a client's editable fields."""
        stored = await self._clients.require_in_org(organization_id, client_id)
        for field, value in fields.items():
            if field in _EDITABLE_FIELDS and value is not None:
                setattr(stored, field, value)
        stored.updated_by = UUID(actor_id) if actor_id else None
        return await self._clients.update(stored)


__all__ = ["ClientService"]
