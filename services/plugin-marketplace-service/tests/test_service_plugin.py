"""Tests for :class:`app.services.plugin.PluginService` -- registration and
the full Registration -> Validation -> Publishing -> Approval lifecycle.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.manifests.engine import compute_manifest_checksum
from app.models.enums import (
    ManifestValidationStatus,
    PluginCategory,
    PluginLifecycleStatus,
    PluginType,
)
from app.repositories.manifest import PluginManifestRepository
from app.repositories.plugin import PluginRepository, PluginVersionRepository
from app.services.plugin import PluginService


def _manifest(version: str = "1.0.0", **overrides: Any) -> dict[str, Any]:
    """A real, checksummed manifest for *version* -- the checksum is
    computed the same way ``PluginService.submit_manifest`` re-derives it,
    so it always validates unless a test deliberately corrupts a field.
    """
    manifest: dict[str, Any] = {
        "name": "Manifest Plugin",
        "publisher": "manifest-publisher",
        "category": PluginCategory.UTILITIES.value,
        "type": PluginType.CUSTOM_PLUGIN.value,
        "version": version,
        "entry_points": ["main:run"],
        "supported_platform_versions": [
            {"platform": "aiios", "version_constraint": ">=1.0.0,<2.0.0"}
        ],
        "permissions_required": [],
        "dependencies": [],
        "api_requirements": [],
        "health_checks": [],
    }
    manifest.update(overrides)
    manifest["checksum"] = compute_manifest_checksum(manifest)
    return manifest


class TestRegister:
    async def test_register_success(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="register-happy",
            name="Register Happy",
            category=PluginCategory.AUTOMATION,
            plugin_type=PluginType.CONNECTOR,
            description="A test plugin.",
            homepage_url="https://example.com/plugin",
            license_name="MIT",
            tags=["a", "b"],
            owner_id="owner-1",
        )
        assert plugin.organization_id == organization_id
        assert plugin.slug == "register-happy"
        assert plugin.name == "Register Happy"
        assert plugin.category == PluginCategory.AUTOMATION
        assert plugin.plugin_type == PluginType.CONNECTOR
        assert plugin.description == "A test plugin."
        assert plugin.homepage_url == "https://example.com/plugin"
        assert plugin.license == "MIT"
        assert plugin.tags == ["a", "b"]
        assert plugin.owner_id == "owner-1"
        assert plugin.status == PluginLifecycleStatus.REGISTERED
        assert plugin.current_version_number is None

    async def test_register_defaults(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="register-defaults",
            name="Register Defaults",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        assert plugin.tags == []
        assert plugin.publisher_id is None
        assert plugin.description is None

    async def test_register_duplicate_slug_raises(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        await plugin_service.register(
            organization_id,
            slug="dup-slug",
            name="First",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        with pytest.raises(ValidationError, match="already registered"):
            await plugin_service.register(
                organization_id,
                slug="dup-slug",
                name="Second",
                category=PluginCategory.AUTOMATION,
                plugin_type=PluginType.CONNECTOR,
            )

    async def test_register_fires_registered_event(
        self, plugin_service: PluginService, organization_id: uuid.UUID, publisher: Any
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="event-plugin",
            name="Event Plugin",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        assert publisher.names == ["PluginRegistered"]
        event = publisher.events[0]
        assert event.organization_id == organization_id
        assert event.payload == {"plugin_id": str(plugin.id), "slug": "event-plugin"}

    async def test_register_without_event_publisher_does_not_raise(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        manifests_repo: PluginManifestRepository,
        organization_id: uuid.UUID,
    ) -> None:
        """A service built with ``publish_event=None`` -- the default --
        still registers a plugin; it just never announces the event.
        """
        service = PluginService(plugins_repo, versions_repo, manifests_repo, publish_event=None)
        plugin = await service.register(
            organization_id,
            slug="no-publisher",
            name="No Publisher",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        assert plugin.status == PluginLifecycleStatus.REGISTERED


class TestGetAndList:
    async def test_get_not_found_raises(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await plugin_service.get(organization_id, uuid.uuid4())

    async def test_list_for_org_filters_by_category_and_status(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        automation_plugin = await plugin_service.register(
            organization_id,
            slug="list-automation",
            name="Automation One",
            category=PluginCategory.AUTOMATION,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        utility_plugin = await plugin_service.register(
            organization_id,
            slug="list-utility",
            name="Utility One",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )

        all_plugins = await plugin_service.list_for_org(organization_id)
        assert {p.id for p in all_plugins} == {automation_plugin.id, utility_plugin.id}

        automation_only = await plugin_service.list_for_org(
            organization_id, category=PluginCategory.AUTOMATION
        )
        assert [p.id for p in automation_only] == [automation_plugin.id]

        await plugin_service.archive(organization_id, utility_plugin.id)

        archived_only = await plugin_service.list_for_org(
            organization_id, status=PluginLifecycleStatus.ARCHIVED
        )
        assert [p.id for p in archived_only] == [utility_plugin.id]

        registered_only = await plugin_service.list_for_org(
            organization_id, status=PluginLifecycleStatus.REGISTERED
        )
        assert [p.id for p in registered_only] == [automation_plugin.id]


class TestUpdateMetadata:
    async def test_update_metadata_partial_updates(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="meta-plugin",
            name="Meta Plugin",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
            description="original description",
            homepage_url="https://original.example.com",
            tags=["a", "b"],
        )

        after_description = await plugin_service.update_metadata(
            organization_id, plugin.id, description="new description"
        )
        assert after_description.description == "new description"
        assert after_description.homepage_url == "https://original.example.com"
        assert after_description.tags == ["a", "b"]

        after_homepage = await plugin_service.update_metadata(
            organization_id, plugin.id, homepage_url="https://new.example.com"
        )
        assert after_homepage.description == "new description"
        assert after_homepage.homepage_url == "https://new.example.com"
        assert after_homepage.tags == ["a", "b"]

        after_tags = await plugin_service.update_metadata(organization_id, plugin.id, tags=["c"])
        assert after_tags.description == "new description"
        assert after_tags.homepage_url == "https://new.example.com"
        assert after_tags.tags == ["c"]

    async def test_update_metadata_not_found_raises(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await plugin_service.update_metadata(organization_id, uuid.uuid4(), description="x")


class TestSubmitManifest:
    async def test_submit_manifest_happy_path(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="submit-happy",
            name="Submit Happy",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        version, manifest_entry = await plugin_service.submit_manifest(
            organization_id,
            plugin.id,
            version_number="1.0.0",
            manifest=_manifest("1.0.0"),
            changelog="Initial release",
            released_by="tester",
        )
        assert version.plugin_id == plugin.id
        assert version.version_number == "1.0.0"
        assert version.changelog == "Initial release"
        assert version.released_by == "tester"
        assert version.entry_points == ["main:run"]
        assert version.is_current is False

        assert manifest_entry.plugin_version_id == version.id
        assert manifest_entry.validation_status == ManifestValidationStatus.VALID
        assert manifest_entry.validation_errors == []
        assert manifest_entry.publisher_name == "manifest-publisher"

        refreshed = await plugin_service.get(organization_id, plugin.id)
        assert refreshed.status == PluginLifecycleStatus.VALIDATED

    async def test_submit_manifest_not_newer_than_current_raises(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="submit-notnewer",
            name="Submit Not Newer",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        await plugin_service.submit_manifest(
            organization_id, plugin.id, version_number="1.0.0", manifest=_manifest("1.0.0")
        )
        await plugin_service.publish(organization_id, plugin.id, version_number="1.0.0")

        with pytest.raises(ValidationError, match="not newer"):
            await plugin_service.submit_manifest(
                organization_id, plugin.id, version_number="0.5.0", manifest=_manifest("0.5.0")
            )

    async def test_submit_manifest_duplicate_version_raises(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="submit-dup",
            name="Submit Dup",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        await plugin_service.submit_manifest(
            organization_id, plugin.id, version_number="1.0.0", manifest=_manifest("1.0.0")
        )
        with pytest.raises(ValidationError, match="already exists"):
            await plugin_service.submit_manifest(
                organization_id, plugin.id, version_number="1.0.0", manifest=_manifest("1.0.0")
            )

    async def test_submit_manifest_invalid_manifest_creates_invalid_entry(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="submit-invalid",
            name="Submit Invalid",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        broken_manifest = {"name": "Broken Plugin"}
        version, manifest_entry = await plugin_service.submit_manifest(
            organization_id, plugin.id, version_number="1.0.0", manifest=broken_manifest
        )
        assert version.version_number == "1.0.0"
        assert manifest_entry.validation_status == ManifestValidationStatus.INVALID
        assert len(manifest_entry.validation_errors) > 0

        refreshed = await plugin_service.get(organization_id, plugin.id)
        assert refreshed.status == PluginLifecycleStatus.REGISTERED


class TestPublish:
    async def test_publish_happy_path(
        self, plugin_service: PluginService, organization_id: uuid.UUID, publisher: Any
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="publish-happy",
            name="Publish Happy",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        await plugin_service.submit_manifest(
            organization_id, plugin.id, version_number="1.0.0", manifest=_manifest("1.0.0")
        )
        published = await plugin_service.publish(organization_id, plugin.id, version_number="1.0.0")

        assert published.status == PluginLifecycleStatus.PUBLISHED
        assert published.current_version_number == "1.0.0"

        assert "PluginPublished" in publisher.names
        event = next(e for e in publisher.events if e.event_name == "PluginPublished")
        assert event.payload == {"plugin_id": str(plugin.id), "version_number": "1.0.0"}

    async def test_publish_never_submitted_version_raises(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="publish-neversubmitted",
            name="Publish Never Submitted",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        with pytest.raises(ValidationError, match="never submitted"):
            await plugin_service.publish(organization_id, plugin.id, version_number="1.0.0")

    async def test_publish_never_validated_manifest_raises(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="publish-neverval",
            name="Publish Never Validated",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        await plugin_service.submit_manifest(
            organization_id, plugin.id, version_number="1.0.0", manifest={"name": "Broken"}
        )
        with pytest.raises(ValidationError, match="validated manifest"):
            await plugin_service.publish(organization_id, plugin.id, version_number="1.0.0")

    async def test_publish_switches_current_version(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="publish-switch",
            name="Publish Switch",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        await plugin_service.submit_manifest(
            organization_id, plugin.id, version_number="1.0.0", manifest=_manifest("1.0.0")
        )
        await plugin_service.publish(organization_id, plugin.id, version_number="1.0.0")

        await plugin_service.submit_manifest(
            organization_id, plugin.id, version_number="1.1.0", manifest=_manifest("1.1.0")
        )
        published = await plugin_service.publish(organization_id, plugin.id, version_number="1.1.0")
        assert published.current_version_number == "1.1.0"

        versions = {
            v.version_number: v
            for v in await plugin_service.list_versions(organization_id, plugin.id)
        }
        assert versions["1.1.0"].is_current is True
        assert versions["1.0.0"].is_current is False


class TestLifecycleTransitions:
    async def test_submit_for_approval_and_approve(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="lifecycle-approve",
            name="Lifecycle Approve",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        pending = await plugin_service.submit_for_approval(organization_id, plugin.id)
        assert pending.status == PluginLifecycleStatus.PENDING_APPROVAL

        approved = await plugin_service.approve(organization_id, plugin.id)
        assert approved.status == PluginLifecycleStatus.APPROVED

    async def test_submit_for_approval_and_reject(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="lifecycle-reject",
            name="Lifecycle Reject",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        await plugin_service.submit_for_approval(organization_id, plugin.id)
        rejected = await plugin_service.reject(organization_id, plugin.id)
        assert rejected.status == PluginLifecycleStatus.REJECTED

    async def test_deprecate(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="lifecycle-deprecate",
            name="Lifecycle Deprecate",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        deprecated = await plugin_service.deprecate(organization_id, plugin.id)
        assert deprecated.status == PluginLifecycleStatus.DEPRECATED

    async def test_archive(self, plugin_service: PluginService, organization_id: uuid.UUID) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="lifecycle-archive",
            name="Lifecycle Archive",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        archived = await plugin_service.archive(organization_id, plugin.id)
        assert archived.status == PluginLifecycleStatus.ARCHIVED


class TestListVersions:
    async def test_list_versions_ordering(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugin_service.register(
            organization_id,
            slug="versions-order",
            name="Versions Order",
            category=PluginCategory.UTILITIES,
            plugin_type=PluginType.CUSTOM_PLUGIN,
        )
        await plugin_service.submit_manifest(
            organization_id, plugin.id, version_number="1.0.0", manifest=_manifest("1.0.0")
        )
        await asyncio.sleep(0.01)
        await plugin_service.submit_manifest(
            organization_id, plugin.id, version_number="2.0.0", manifest=_manifest("2.0.0")
        )

        versions = await plugin_service.list_versions(organization_id, plugin.id)
        assert [v.version_number for v in versions] == ["2.0.0", "1.0.0"]

    async def test_list_versions_not_found_propagates(
        self, plugin_service: PluginService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await plugin_service.list_versions(organization_id, uuid.uuid4())
