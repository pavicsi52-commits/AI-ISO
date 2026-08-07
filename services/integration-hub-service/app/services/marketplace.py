"""The connector marketplace/catalog (docs/058 "MARKETPLACE", "BUILT-IN CONNECTORS")."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError
from shared_core.plugins.versioning import is_compatible

from app.events.hub_events import SOURCE_SERVICE, MarketplaceUpdatedEvent
from app.models.enums import ConnectorCategory, MarketplaceStatus
from app.models.marketplace import ConnectorMarketplaceEntry
from app.repositories.marketplace import ConnectorMarketplaceRepository
from app.types import EventPublisher

_MIN_RATING = 1.0
_MAX_RATING = 5.0

_BUILTIN_CONNECTORS: dict[ConnectorCategory, tuple[str, ...]] = {
    ConnectorCategory.CLOUD: (
        "AWS",
        "Microsoft Azure",
        "Google Cloud Platform",
        "Oracle Cloud Infrastructure",
        "OpenStack",
        "VMware Cloud",
    ),
    ConnectorCategory.VIRTUALIZATION: (
        "VMware vCenter",
        "VMware ESXi",
        "Proxmox VE",
        "Microsoft Hyper-V",
        "Nutanix AHV",
        "KVM",
    ),
    ConnectorCategory.CONTAINER_PLATFORMS: (
        "Kubernetes",
        "OpenShift",
        "Rancher",
        "Docker",
        "Docker Swarm",
    ),
    ConnectorCategory.IDENTITY: (
        "LDAP",
        "Microsoft Active Directory",
        "Keycloak",
        "Azure Active Directory",
        "Okta",
    ),
    ConnectorCategory.DEVOPS: (
        "GitHub",
        "GitLab",
        "Azure DevOps",
        "Bitbucket",
        "Jenkins",
        "Argo CD",
        "FluxCD",
        "Harbor",
    ),
    ConnectorCategory.ITSM: (
        "ServiceNow",
        "Jira",
        "Freshservice",
        "BMC Helix",
        "ManageEngine ServiceDesk",
    ),
    ConnectorCategory.MONITORING: (
        "Prometheus",
        "Grafana",
        "Zabbix",
        "Nagios",
        "Datadog",
        "New Relic",
        "Elastic",
        "Splunk",
    ),
    ConnectorCategory.INDUSTRIAL_PROTOCOLS: (
        "Redfish",
        "IPMI",
        "SNMP",
        "OPC UA",
        "MQTT",
        "Modbus TCP",
        "BACnet",
        "EtherNet/IP",
        "PROFINET",
    ),
    ConnectorCategory.DATABASES: (
        "PostgreSQL",
        "MySQL",
        "MariaDB",
        "Microsoft SQL Server",
        "Oracle Database",
        "MongoDB",
        "Neo4j",
        "Redis",
    ),
    ConnectorCategory.MESSAGING: (
        "Kafka",
        "RabbitMQ",
        "NATS",
        "ActiveMQ",
        "MQTT Broker",
    ),
    ConnectorCategory.STORAGE: (
        "MinIO",
        "Ceph",
        "NetApp",
        "Dell PowerStore",
        "Pure Storage",
    ),
    ConnectorCategory.CUSTOM: (
        "REST API",
        "SOAP",
        "GraphQL",
        "Webhook",
        "gRPC",
        "Custom SDK Connector",
    ),
}
"""Docs/058's own "BUILT-IN CONNECTORS" list, verbatim. Networking, Storage,
Security, and Business Applications are named categories with no named
connectors of their own in that section -- represented in
``connector_categories`` (seeded by ``ConnectorService
.ensure_default_categories``) but with no built-in catalog entries here."""


def slugify(name: str) -> str:
    """A stable, URL-safe id for a connector name (``"VMware vCenter"`` -> ``"vmware_vcenter"``)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class MarketplaceService:
    """The installable connector catalog."""

    def __init__(
        self,
        marketplace: ConnectorMarketplaceRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._marketplace = marketplace
        self._publish = publish_event

    async def seed_builtin_catalog(self, organization_id: UUID) -> int:
        """Idempotently register every built-in connector for a fresh organization.

        Returns the number of entries actually created (0 on a re-run
        against an organization that already has them).
        """
        created = 0
        for category, names in _BUILTIN_CONNECTORS.items():
            for name in names:
                slug = slugify(name)
                if await self._marketplace.get_by_slug(organization_id, slug) is not None:
                    continue
                await self._marketplace.create(
                    ConnectorMarketplaceEntry(
                        organization_id=organization_id,
                        slug=slug,
                        name=name,
                        category=category,
                        built_in=True,
                        status=MarketplaceStatus.PUBLISHED,
                    )
                )
                created += 1
        return created

    async def publish(
        self,
        organization_id: UUID,
        *,
        slug: str,
        name: str,
        category: ConnectorCategory,
        description: str | None = None,
        publisher: str = "AI-IOS",
        version_number: str = "1.0.0",
        supported_auth_methods: list[str] | None = None,
        dependencies: list[str] | None = None,
        published_by: str | None = None,
    ) -> ConnectorMarketplaceEntry:
        """Publish a new (non-built-in) connector to this organization's own catalog.

        Raises:
            ValidationError: If *slug* is already published, or a
                declared dependency's own slug is not itself published.
        """
        if await self._marketplace.get_by_slug(organization_id, slug) is not None:
            raise ValidationError(f"A marketplace entry with slug {slug!r} already exists.")
        for dependency_slug in dependencies or []:
            if await self._marketplace.get_by_slug(organization_id, dependency_slug) is None:
                raise ValidationError(f"Dependency {dependency_slug!r} is not published.")
        entry = await self._marketplace.create(
            ConnectorMarketplaceEntry(
                organization_id=organization_id,
                slug=slug,
                name=name,
                category=category,
                description=description,
                publisher=publisher,
                latest_version_number=version_number,
                supported_auth_methods=list(supported_auth_methods or []),
                dependencies=list(dependencies or []),
                published_by=published_by,
                status=MarketplaceStatus.PUBLISHED,
            )
        )
        await self._publish_event(
            MarketplaceUpdatedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"slug": slug, "action": "published"},
            )
        )
        return entry

    async def get(self, organization_id: UUID, entry_id: UUID) -> ConnectorMarketplaceEntry:
        """One catalog entry.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._marketplace.require_in_org(organization_id, entry_id)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        category: ConnectorCategory | None = None,
        status: MarketplaceStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ConnectorMarketplaceEntry]:
        """Catalog entries visible in this organization."""
        return await self._marketplace.list_for_org(
            organization_id,
            category=str(category) if category else None,
            status=status,
            limit=limit,
            offset=offset,
        )

    def check_compatible(self, entry: ConnectorMarketplaceEntry, *, constraint: str) -> bool:
        """Whether *entry*'s own ``latest_version_number`` satisfies a caller's *constraint*."""
        return is_compatible(entry.latest_version_number, constraint)

    async def record_install(
        self, organization_id: UUID, entry_id: UUID
    ) -> ConnectorMarketplaceEntry:
        """Bump a catalog entry's own install count, when a connector is registered from it."""
        entry = await self.get(organization_id, entry_id)
        entry.install_count += 1
        return await self._marketplace.update(entry)

    async def rate(
        self, organization_id: UUID, entry_id: UUID, *, rating: float
    ) -> ConnectorMarketplaceEntry:
        """Record a ``1``-``5`` rating for a catalog entry.

        Raises:
            ValidationError: If *rating* is out of range.
        """
        if not _MIN_RATING <= rating <= _MAX_RATING:
            raise ValidationError("Rating must be between 1 and 5.")
        entry = await self.get(organization_id, entry_id)
        entry.rating_total += rating
        entry.rating_count += 1
        return await self._marketplace.update(entry)

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)


__all__ = ["MarketplaceService", "slugify"]
