"""Tests for ``app.services.marketplace.PluginMarketplaceService``."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import MarketplaceListingStatus
from app.services.marketplace import PluginMarketplaceService
from tests.conftest import MakePluginFn, RecordingPublisher


async def test_create_listing_happy_path(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="marketplace-plugin")

    listing = await marketplace_service.create_listing(
        organization_id,
        plugin.id,
        search_keywords=["automation", "widget"],
        icon_url="https://example.test/icon.png",
        screenshots=["https://example.test/shot1.png"],
        pricing_summary="Free",
    )

    assert listing.status == MarketplaceListingStatus.DRAFT
    assert listing.plugin_id == plugin.id
    assert listing.search_keywords == ["automation", "widget"]
    assert listing.icon_url == "https://example.test/icon.png"
    assert listing.screenshots == ["https://example.test/shot1.png"]
    assert listing.pricing_summary == "Free"
    assert listing.featured is False
    assert listing.install_count == 0


async def test_create_second_listing_for_same_plugin_raises(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="marketplace-dup-plugin")
    await marketplace_service.create_listing(organization_id, plugin.id)

    with pytest.raises(ValidationError):
        await marketplace_service.create_listing(organization_id, plugin.id)


async def test_approve_sets_published_and_emits_event(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
    publisher: RecordingPublisher,
) -> None:
    plugin = await make_plugin(slug="marketplace-approve-plugin")
    listing = await marketplace_service.create_listing(organization_id, plugin.id)
    publisher.events.clear()

    approved = await marketplace_service.approve(organization_id, listing.id, approved_by="admin-1")

    assert approved.status == MarketplaceListingStatus.PUBLISHED
    assert approved.approved_by == "admin-1"
    assert approved.approved_at is not None
    assert approved.listed_at is not None

    assert publisher.names == ["MarketplaceUpdated"]
    event = publisher.events[0]
    assert event.payload["plugin_id"] == str(plugin.id)
    assert event.payload["action"] == "published"


async def test_reject_sets_removed_with_reason(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="marketplace-reject-plugin")
    listing = await marketplace_service.create_listing(organization_id, plugin.id)

    rejected = await marketplace_service.reject(listing.id, reason="Policy violation")

    assert rejected.status == MarketplaceListingStatus.REMOVED
    assert rejected.rejection_reason == "Policy violation"


async def test_feature_and_unfeature_toggle_status(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="marketplace-feature-plugin")
    listing = await marketplace_service.create_listing(organization_id, plugin.id)
    await marketplace_service.approve(organization_id, listing.id)

    featured = await marketplace_service.feature(listing.id)
    assert featured.status == MarketplaceListingStatus.FEATURED
    assert featured.featured is True

    unfeatured = await marketplace_service.unfeature(listing.id)
    assert unfeatured.status == MarketplaceListingStatus.PUBLISHED
    assert unfeatured.featured is False


async def test_deprecate_sets_deprecated(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="marketplace-deprecate-plugin")
    listing = await marketplace_service.create_listing(organization_id, plugin.id)
    await marketplace_service.approve(organization_id, listing.id)

    deprecated = await marketplace_service.deprecate(listing.id)

    assert deprecated.status == MarketplaceListingStatus.DEPRECATED


async def test_record_install_increments_counters(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="marketplace-install-plugin")
    await marketplace_service.create_listing(organization_id, plugin.id)

    first = await marketplace_service.record_install(plugin.id)
    assert first is not None
    assert first.install_count == 1
    assert first.active_install_count == 1

    second = await marketplace_service.record_install(plugin.id)
    assert second is not None
    assert second.install_count == 2
    assert second.active_install_count == 2


async def test_record_install_returns_none_when_no_listing(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="marketplace-no-listing-plugin")

    result = await marketplace_service.record_install(plugin.id)

    assert result is None


async def test_search_query_filters_by_search_keywords(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    automation_plugin = await make_plugin(slug="search-automation-plugin")
    reporting_plugin = await make_plugin(slug="search-reporting-plugin")

    automation_listing = await marketplace_service.create_listing(
        organization_id, automation_plugin.id, search_keywords=["automation", "workflow"]
    )
    reporting_listing = await marketplace_service.create_listing(
        organization_id, reporting_plugin.id, search_keywords=["reporting", "analytics"]
    )
    await marketplace_service.approve(organization_id, automation_listing.id)
    await marketplace_service.approve(organization_id, reporting_listing.id)

    automation_results = await marketplace_service.search(query="automation")
    assert {r.id for r in automation_results} == {automation_listing.id}

    reporting_results = await marketplace_service.search(query="analytics")
    assert {r.id for r in reporting_results} == {reporting_listing.id}


async def test_search_featured_only_filters(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plain_plugin = await make_plugin(slug="search-plain-plugin")
    featured_plugin = await make_plugin(slug="search-featured-plugin")

    plain_listing = await marketplace_service.create_listing(organization_id, plain_plugin.id)
    featured_listing = await marketplace_service.create_listing(organization_id, featured_plugin.id)
    await marketplace_service.approve(organization_id, plain_listing.id)
    await marketplace_service.approve(organization_id, featured_listing.id)
    await marketplace_service.feature(featured_listing.id)

    all_results = await marketplace_service.search()
    assert {r.id for r in all_results} == {plain_listing.id, featured_listing.id}

    featured_results = await marketplace_service.search(featured_only=True)
    assert {r.id for r in featured_results} == {featured_listing.id}


async def test_search_pagination_limit_and_offset(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    listing_ids: list[uuid.UUID] = []
    for index in range(5):
        plugin = await make_plugin(slug=f"search-page-plugin-{index}")
        listing = await marketplace_service.create_listing(organization_id, plugin.id)
        await marketplace_service.approve(organization_id, listing.id)
        listing_ids.append(listing.id)

    first_page = await marketplace_service.search(limit=2, offset=0)
    second_page = await marketplace_service.search(limit=2, offset=2)
    remainder = await marketplace_service.search(limit=2, offset=4)

    assert len(first_page) == 2
    assert len(second_page) == 2
    assert len(remainder) == 1

    all_ids = {listing.id for listing in (*first_page, *second_page, *remainder)}
    assert all_ids == set(listing_ids)


async def test_list_pending_approval_only_returns_draft(
    marketplace_service: PluginMarketplaceService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    draft_plugin = await make_plugin(slug="pending-draft-plugin")
    approved_plugin = await make_plugin(slug="pending-approved-plugin")

    draft_listing = await marketplace_service.create_listing(organization_id, draft_plugin.id)
    approved_listing = await marketplace_service.create_listing(organization_id, approved_plugin.id)
    await marketplace_service.approve(organization_id, approved_listing.id)

    pending = await marketplace_service.list_pending_approval()
    pending_ids = {listing.id for listing in pending}
    assert draft_listing.id in pending_ids
    assert approved_listing.id not in pending_ids


async def test_approve_reject_feature_unfeature_deprecate_unknown_entry_raises_not_found(
    marketplace_service: PluginMarketplaceService, organization_id: uuid.UUID
) -> None:
    missing_id = uuid.uuid4()
    with pytest.raises(NotFoundError):
        await marketplace_service.approve(organization_id, missing_id)
    with pytest.raises(NotFoundError):
        await marketplace_service.reject(missing_id, reason="nope")
    with pytest.raises(NotFoundError):
        await marketplace_service.feature(missing_id)
    with pytest.raises(NotFoundError):
        await marketplace_service.unfeature(missing_id)
    with pytest.raises(NotFoundError):
        await marketplace_service.deprecate(missing_id)
