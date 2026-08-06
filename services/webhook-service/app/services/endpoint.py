"""Webhook endpoint registration (docs/057 "ENDPOINT MANAGEMENT")."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.models.endpoint import WebhookEndpoint
from app.models.enums import EndpointStatus, WebhookAuthMethod, WebhookKind
from app.repositories.endpoint import WebhookEndpointRepository
from app.security.url_safety import assert_safe_url

_EDITABLE_FIELDS = frozenset(
    {
        "name",
        "description",
        "url",
        "auth_method",
        "headers",
        "status",
        "owner_id",
        "timeout_seconds",
        "max_attempts",
        "backoff_strategy",
        "enabled",
    }
)


class EndpointService:
    """Registered outgoing-delivery targets: registration, editing, and health tracking."""

    def __init__(self, endpoints: WebhookEndpointRepository) -> None:
        self._endpoints = endpoints

    async def register(
        self,
        organization_id: UUID,
        *,
        name: str,
        url: str,
        kind: WebhookKind = WebhookKind.OUTGOING,
        auth_method: WebhookAuthMethod = WebhookAuthMethod.HMAC_SHA256,
        description: str | None = None,
        headers: dict[str, str] | None = None,
        owner_id: str | None = None,
        timeout_seconds: float | None = None,
        max_attempts: int | None = None,
        actor_id: str | None = None,
    ) -> WebhookEndpoint:
        """Register a new outgoing-delivery target.

        Raises:
            ValidationError: If *url* is not http/https, cannot be
                resolved, or resolves to a non-public address.
        """
        await assert_safe_url(url)
        return await self._endpoints.create(
            WebhookEndpoint(
                organization_id=organization_id,
                name=name,
                description=description,
                url=url,
                kind=kind,
                auth_method=auth_method,
                headers=dict(headers or {}),
                owner_id=owner_id,
                timeout_seconds=timeout_seconds,
                max_attempts=max_attempts,
                created_by=UUID(actor_id) if actor_id else None,
            )
        )

    async def get(self, organization_id: UUID, endpoint_id: UUID) -> WebhookEndpoint:
        """One endpoint.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._endpoints.require_in_org(organization_id, endpoint_id)

    async def list_endpoints(
        self, organization_id: UUID, *, enabled: bool | None = None
    ) -> list[WebhookEndpoint]:
        """Endpoints registered in this organization."""
        return await self._endpoints.list_for_org(organization_id, enabled=enabled)

    async def update(
        self, organization_id: UUID, endpoint_id: UUID, *, actor_id: str | None = None, **fields: Any
    ) -> WebhookEndpoint:
        """Edit an endpoint's editable fields.

        Raises:
            ValidationError: If ``url`` is being changed and the new
                value is not http/https or resolves unsafely.
        """
        stored = await self._endpoints.require_in_org(organization_id, endpoint_id)
        if fields.get("url") is not None:
            await assert_safe_url(fields["url"])
        for field, value in fields.items():
            if field in _EDITABLE_FIELDS and value is not None:
                setattr(stored, field, value)
        stored.updated_by = UUID(actor_id) if actor_id else None
        return await self._endpoints.update(stored)

    async def delete(
        self, organization_id: UUID, endpoint_id: UUID, *, actor_id: str | None = None
    ) -> None:
        """Deregister an endpoint."""
        stored = await self._endpoints.require_in_org(organization_id, endpoint_id)
        await self._endpoints.delete(stored.id, deleted_by=UUID(actor_id) if actor_id else None)

    async def record_delivery_outcome(
        self, organization_id: UUID, endpoint_id: UUID, *, succeeded: bool
    ) -> None:
        """Update an endpoint's own rolling health after one delivery attempt."""
        stored = await self._endpoints.require_in_org(organization_id, endpoint_id)
        now = datetime.now(UTC)
        if succeeded:
            stored.consecutive_failures = 0
            stored.last_delivered_at = now
            if stored.status == EndpointStatus.UNHEALTHY:
                stored.status = EndpointStatus.ACTIVE
        else:
            stored.consecutive_failures += 1
            stored.last_failed_at = now
        await self._endpoints.update(stored)


__all__ = ["EndpointService"]
