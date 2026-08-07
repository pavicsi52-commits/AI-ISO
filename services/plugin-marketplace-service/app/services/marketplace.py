"""Marketplace listing management (docs/059 "MARKETPLACE")."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.events.plugin_events import SOURCE_SERVICE, MarketplaceUpdatedEvent
from app.models.enums import MarketplaceListingStatus
from app.models.marketplace import PluginMarketplaceEntry
from app.repositories.marketplace import PluginMarketplaceRepository
from app.types import EventPublisher


class PluginMarketplaceService:
    """Creates, publishes, features, approves, and searches marketplace listings."""

    def __init__(
        self,
        marketplace: PluginMarketplaceRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._marketplace = marketplace
        self._publish = publish_event

    async def create_listing(
        self,
        organization_id: UUID,
        plugin_id: UUID,
        *,
        search_keywords: list[str] | None = None,
        icon_url: str | None = None,
        screenshots: list[str] | None = None,
        pricing_summary: str | None = None,
    ) -> PluginMarketplaceEntry:
        """Create a draft marketplace listing for a plugin.

        Raises:
            ValidationError: If a listing for this plugin already exists.
        """
        if await self._marketplace.get_for_plugin(plugin_id) is not None:
            raise ValidationError(f"Plugin {plugin_id} already has a marketplace listing.")
        return await self._marketplace.create(
            PluginMarketplaceEntry(
                organization_id=organization_id,
                plugin_id=plugin_id,
                status=MarketplaceListingStatus.DRAFT,
                search_keywords=list(search_keywords or []),
                icon_url=icon_url,
                screenshots=list(screenshots or []),
                pricing_summary=pricing_summary,
            )
        )

    async def approve(
        self, organization_id: UUID, entry_id: UUID, *, approved_by: str | None = None
    ) -> PluginMarketplaceEntry:
        """Approve a draft listing, publishing it to the marketplace."""
        entry = await self._marketplace.require_by_id(entry_id)
        entry.status = MarketplaceListingStatus.PUBLISHED
        entry.approved_by = approved_by
        entry.approved_at = datetime.now(UTC)
        entry.listed_at = datetime.now(UTC)
        entry = await self._marketplace.update(entry)
        await self._publish_event(
            MarketplaceUpdatedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"plugin_id": str(entry.plugin_id), "action": "published"},
            )
        )
        return entry

    async def reject(self, entry_id: UUID, *, reason: str) -> PluginMarketplaceEntry:
        """Reject a draft listing."""
        entry = await self._marketplace.require_by_id(entry_id)
        entry.status = MarketplaceListingStatus.REMOVED
        entry.rejection_reason = reason
        return await self._marketplace.update(entry)

    async def feature(self, entry_id: UUID) -> PluginMarketplaceEntry:
        """Feature a published listing."""
        entry = await self._marketplace.require_by_id(entry_id)
        entry.status = MarketplaceListingStatus.FEATURED
        entry.featured = True
        return await self._marketplace.update(entry)

    async def unfeature(self, entry_id: UUID) -> PluginMarketplaceEntry:
        """Return a featured listing to plain published status."""
        entry = await self._marketplace.require_by_id(entry_id)
        entry.status = MarketplaceListingStatus.PUBLISHED
        entry.featured = False
        return await self._marketplace.update(entry)

    async def deprecate(self, entry_id: UUID) -> PluginMarketplaceEntry:
        """Deprecate a listing."""
        entry = await self._marketplace.require_by_id(entry_id)
        entry.status = MarketplaceListingStatus.DEPRECATED
        return await self._marketplace.update(entry)

    async def record_install(self, plugin_id: UUID) -> PluginMarketplaceEntry | None:
        """Bump a listing's own install counters after a successful install."""
        entry = await self._marketplace.get_for_plugin(plugin_id)
        if entry is None:
            return None
        entry.install_count += 1
        entry.active_install_count += 1
        return await self._marketplace.update(entry)

    async def search(
        self,
        *,
        query: str | None = None,
        featured_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PluginMarketplaceEntry]:
        """Search the public marketplace."""
        return await self._marketplace.list_published(
            search=query, featured_only=featured_only, limit=limit, offset=offset
        )

    async def list_pending_approval(self, *, limit: int = 200) -> list[PluginMarketplaceEntry]:
        """Every draft listing awaiting the marketplace-approval sweep."""
        return await self._marketplace.list_pending_approval(limit=limit)

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)


__all__ = ["PluginMarketplaceService"]
