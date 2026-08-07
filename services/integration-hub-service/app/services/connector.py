"""Connector registration and lifecycle management (docs/058 "CONNECTOR LIFECYCLE")."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError
from shared_core.plugins.versioning import is_downgrade, is_upgrade, parse_version

from app.models.connector import Connector, ConnectorCategoryEntry, ConnectorVersion
from app.models.enums import ConnectorAuthMethod, ConnectorCategory, ConnectorLifecycleStatus
from app.repositories.connector import (
    ConnectorCategoryRepository,
    ConnectorRepository,
    ConnectorVersionRepository,
)


class ConnectorService:
    """Registers, configures, and moves a connector instance through its own lifecycle."""

    def __init__(
        self,
        connectors: ConnectorRepository,
        versions: ConnectorVersionRepository,
        categories: ConnectorCategoryRepository,
    ) -> None:
        self._connectors = connectors
        self._versions = versions
        self._categories = categories

    async def register(
        self,
        organization_id: UUID,
        *,
        name: str,
        category: ConnectorCategory,
        connector_type: str,
        auth_method: ConnectorAuthMethod = ConnectorAuthMethod.API_KEY,
        marketplace_entry_id: UUID | None = None,
        description: str | None = None,
        owner_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Connector:
        """Register a new connector instance -- the lifecycle's own first stage."""
        return await self._connectors.create(
            Connector(
                organization_id=organization_id,
                name=name,
                category=category,
                connector_type=connector_type,
                auth_method=auth_method,
                marketplace_entry_id=marketplace_entry_id,
                description=description,
                owner_id=owner_id,
                tags=list(tags or []),
                status=ConnectorLifecycleStatus.REGISTERED,
            )
        )

    async def get(self, organization_id: UUID, connector_id: UUID) -> Connector:
        """One connector.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._connectors.require_in_org(organization_id, connector_id)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        category: ConnectorCategory | None = None,
        status: ConnectorLifecycleStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Connector]:
        """Connectors in this organization, newest first."""
        return await self._connectors.list_for_org(
            organization_id,
            category=str(category) if category else None,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def install(
        self, organization_id: UUID, connector_id: UUID, *, version_number: str = "1.0.0"
    ) -> Connector:
        """Move a registered connector into ``INSTALLED``, recording its first version."""
        connector = await self.get(organization_id, connector_id)
        parse_version(version_number)
        connector.status = ConnectorLifecycleStatus.INSTALLED
        connector.current_version_number = version_number
        await self._connectors.update(connector)
        await self._versions.create(
            ConnectorVersion(
                organization_id=organization_id,
                connector_id=connector.id,
                version_number=version_number,
                config_snapshot=dict(connector.config),
                installed_at=datetime.now(UTC),
                is_current=True,
            )
        )
        return connector

    async def configure(
        self, organization_id: UUID, connector_id: UUID, *, config: dict[str, Any]
    ) -> Connector:
        """Update a connector's own configuration, moving it into ``CONFIGURED``."""
        connector = await self.get(organization_id, connector_id)
        connector.config = dict(config)
        connector.status = ConnectorLifecycleStatus.CONFIGURED
        return await self._connectors.update(connector)

    async def mark_validated(self, organization_id: UUID, connector_id: UUID) -> Connector:
        """Move a connector into ``VALIDATED`` -- called after a successful test connection."""
        connector = await self.get(organization_id, connector_id)
        connector.status = ConnectorLifecycleStatus.VALIDATED
        connector.last_validated_at = datetime.now(UTC)
        return await self._connectors.update(connector)

    async def enable(self, organization_id: UUID, connector_id: UUID) -> Connector:
        """Enable a connector -- it becomes eligible for sync/flow/health-probe activity."""
        connector = await self.get(organization_id, connector_id)
        connector.enabled = True
        connector.status = ConnectorLifecycleStatus.ENABLED
        return await self._connectors.update(connector)

    async def disable(self, organization_id: UUID, connector_id: UUID) -> Connector:
        """Disable a connector."""
        connector = await self.get(organization_id, connector_id)
        connector.enabled = False
        connector.status = ConnectorLifecycleStatus.DISABLED
        return await self._connectors.update(connector)

    async def upgrade(
        self, organization_id: UUID, connector_id: UUID, *, version_number: str
    ) -> Connector:
        """Move a connector onto a newer version, snapshotting the transition.

        Raises:
            ValidationError: If *version_number* is not strictly newer
                than the connector's own current version.
        """
        connector = await self.get(organization_id, connector_id)
        if connector.current_version_number and not is_upgrade(
            connector.current_version_number, version_number
        ):
            raise ValidationError(
                f"{version_number!r} is not newer than the current version "
                f"{connector.current_version_number!r}."
            )
        return await self._switch_version(connector, version_number)

    async def rollback(
        self, organization_id: UUID, connector_id: UUID, *, version_number: str
    ) -> Connector:
        """Move a connector back onto an older, previously-installed version.

        Raises:
            ValidationError: If *version_number* is not strictly older
                than the connector's own current version, or was never
                actually installed.
        """
        connector = await self.get(organization_id, connector_id)
        if connector.current_version_number and not is_downgrade(
            connector.current_version_number, version_number
        ):
            raise ValidationError(
                f"{version_number!r} is not older than the current version "
                f"{connector.current_version_number!r}."
            )
        history = await self._versions.list_for_connector(connector.id)
        if not any(v.version_number == version_number for v in history):
            raise ValidationError(
                f"Version {version_number!r} was never installed on this connector."
            )
        return await self._switch_version(connector, version_number)

    async def _switch_version(self, connector: Connector, version_number: str) -> Connector:
        current = await self._versions.get_current(connector.id)
        if current is not None:
            current.is_current = False
            await self._versions.update(current)
        existing = next(
            (
                v
                for v in await self._versions.list_for_connector(connector.id)
                if v.version_number == version_number
            ),
            None,
        )
        if existing is not None:
            existing.is_current = True
            await self._versions.update(existing)
        else:
            await self._versions.create(
                ConnectorVersion(
                    organization_id=connector.organization_id,
                    connector_id=connector.id,
                    version_number=version_number,
                    config_snapshot=dict(connector.config),
                    installed_at=datetime.now(UTC),
                    is_current=True,
                )
            )
        connector.current_version_number = version_number
        return await self._connectors.update(connector)

    async def deprecate(self, organization_id: UUID, connector_id: UUID) -> Connector:
        """Mark a connector deprecated -- still usable, flagged for eventual removal."""
        connector = await self.get(organization_id, connector_id)
        connector.status = ConnectorLifecycleStatus.DEPRECATED
        connector.enabled = False
        return await self._connectors.update(connector)

    async def remove(self, organization_id: UUID, connector_id: UUID) -> Connector:
        """Mark a connector removed -- the terminal lifecycle stage."""
        connector = await self.get(organization_id, connector_id)
        connector.status = ConnectorLifecycleStatus.REMOVED
        connector.enabled = False
        return await self._connectors.update(connector)

    async def list_versions(
        self, organization_id: UUID, connector_id: UUID
    ) -> list[ConnectorVersion]:
        """One connector's own upgrade/rollback history, newest first.

        Raises:
            NotFoundError: If the connector does not exist here.
        """
        connector = await self.get(organization_id, connector_id)
        return await self._versions.list_for_connector(connector.id)

    async def record_health_outcome(self, connector: Connector, *, succeeded: bool) -> Connector:
        """Update a connector's own consecutive-failure counter after one health probe."""
        connector.consecutive_failures = 0 if succeeded else connector.consecutive_failures + 1
        connector.last_health_check_at = datetime.now(UTC)
        return await self._connectors.update(connector)

    async def list_categories(self, organization_id: UUID) -> list[ConnectorCategoryEntry]:
        """Categories visible in this organization."""
        return await self._categories.list_for_org(organization_id)

    async def ensure_default_categories(self, organization_id: UUID) -> None:
        """Seed the fifteen built-in categories for a fresh organization, idempotently."""
        for category in ConnectorCategory:
            if await self._categories.get_by_name(organization_id, str(category)) is None:
                await self._categories.create(
                    ConnectorCategoryEntry(
                        organization_id=organization_id, name=category, built_in=True
                    )
                )


__all__ = ["ConnectorService"]
