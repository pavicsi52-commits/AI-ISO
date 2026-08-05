"""Backend service registration.

Registering, editing, or deregistering a service is an administrative
operation recorded through :class:`~app.services.reporting.AuditService`
(at the API layer, alongside every other admin action) -- none of
docs/056's own eight literal domain events
(``ApiRequestReceived``/``ApiRequestCompleted``/
``ApiAuthenticationFailed``/``ApiAuthorizationDenied``/
``RateLimitExceeded``/``QuotaExceeded``/``CircuitBreakerOpened``/
``GatewayHealthChanged``) describe "a service was registered," so this
service does not invent a ninth one -- the audit trail is the correct,
already-established mechanism for administrative-change history.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import LoadBalancingStrategy
from app.models.service import ApiService
from app.repositories.service import ApiServiceRepository

_EDITABLE_FIELDS = frozenset(
    {
        "description",
        "instances",
        "load_balancing_strategy",
        "health_check_path",
        "timeout_seconds",
        "circuit_breaker_enabled",
        "enabled",
    }
)


class ServiceRegistryService:
    """Registered backend services: registration, editing, and lookup."""

    def __init__(self, services: ApiServiceRepository) -> None:
        self._services = services

    async def register(
        self,
        organization_id: UUID,
        *,
        name: str,
        instances: list[dict[str, Any]],
        description: str | None = None,
        load_balancing_strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN,
        health_check_path: str = "/health",
        timeout_seconds: float | None = None,
        circuit_breaker_enabled: bool = True,
        actor_id: str | None = None,
    ) -> ApiService:
        """Register a new backend service."""
        return await self._services.create(
            ApiService(
                organization_id=organization_id,
                name=name,
                description=description,
                instances=list(instances),
                load_balancing_strategy=load_balancing_strategy,
                health_check_path=health_check_path,
                timeout_seconds=timeout_seconds,
                circuit_breaker_enabled=circuit_breaker_enabled,
                created_by=UUID(actor_id) if actor_id else None,
            )
        )

    async def get(self, organization_id: UUID, service_id: UUID) -> ApiService:
        """One registered service.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._services.require_in_org(organization_id, service_id)

    async def get_by_name(self, organization_id: UUID, name: str) -> ApiService | None:
        """The service registered under *name*, if any."""
        return await self._services.get_by_name(organization_id, name)

    async def list_services(
        self, organization_id: UUID, *, enabled: bool | None = None
    ) -> list[ApiService]:
        """Services registered in this organization."""
        return await self._services.list_for_org(organization_id, enabled=enabled)

    async def update(
        self, organization_id: UUID, service_id: UUID, *, actor_id: str | None = None, **fields: Any
    ) -> ApiService:
        """Edit a service's editable fields.

        Silently ignores any key in *fields* outside the editable set.
        """
        stored = await self._services.require_in_org(organization_id, service_id)
        for field, value in fields.items():
            if field in _EDITABLE_FIELDS and value is not None:
                setattr(stored, field, value)
        stored.updated_by = UUID(actor_id) if actor_id else None
        return await self._services.update(stored)

    async def delete(
        self, organization_id: UUID, service_id: UUID, *, actor_id: str | None = None
    ) -> None:
        """Deregister a service."""
        stored = await self._services.require_in_org(organization_id, service_id)
        await self._services.delete(stored.id, deleted_by=UUID(actor_id) if actor_id else None)


__all__ = ["ServiceRegistryService"]
