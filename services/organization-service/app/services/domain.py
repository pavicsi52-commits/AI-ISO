"""Organization domain management. Per docs/033 "ORGANIZATION SETTINGS": "Allowed Domains"."""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import DomainVerificationStatus
from app.models.organization_domain import OrganizationDomain
from app.repositories.organization_domain import OrganizationDomainRepository


class OrganizationDomainService:
    """Claims, lists, and removes an organization's verified domains."""

    def __init__(self, domains: OrganizationDomainRepository) -> None:
        self._domains = domains

    async def list_for_org(self, organization_id: UUID) -> list[OrganizationDomain]:
        """Every domain claimed by *organization_id*."""
        return await self._domains.list_for_org(organization_id)

    async def claim(
        self, organization_id: UUID, *, domain: str, is_primary: bool
    ) -> OrganizationDomain:
        """Claim *domain* for *organization_id*.

        Raises:
            ConflictError: If *domain* is already claimed by any organization.
        """
        if await self._domains.get_by_domain(domain) is not None:
            raise ConflictError(f"Domain {domain!r} is already claimed.")
        return await self._domains.create(
            OrganizationDomain(
                organization_id=organization_id,
                domain=domain,
                is_primary=is_primary,
                verification_status=DomainVerificationStatus.PENDING,
            )
        )

    async def remove(self, organization_id: UUID, domain_id: UUID) -> None:
        """Remove a domain claim.

        Raises:
            NotFoundError: If no such domain claim exists for *organization_id*.
        """
        record = await self._domains.require_by_id(domain_id)
        if record.organization_id != organization_id:
            raise NotFoundError(f"Domain '{domain_id}' was not found for this organization.")
        await self._domains.delete(domain_id)


__all__ = ["OrganizationDomainService"]
