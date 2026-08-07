"""Repository tests for ``PluginRepository`` and ``PluginVersionRepository``."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import PluginCategory, PluginLifecycleStatus, PluginType
from app.models.plugin import Plugin, PluginVersion
from app.models.publisher import PluginPublisher
from app.repositories.plugin import PluginRepository, PluginVersionRepository
from app.repositories.publisher import PluginPublisherRepository
from tests.conftest import ago, utcnow


def _plugin(organization_id: uuid.UUID, *, slug: str = "plugin", **kwargs: object) -> Plugin:
    defaults: dict[str, object] = {
        "organization_id": organization_id,
        "slug": slug,
        "name": "Test Plugin",
        "category": PluginCategory.UTILITIES,
        "plugin_type": PluginType.CUSTOM_PLUGIN,
    }
    defaults.update(kwargs)
    return Plugin(**defaults)


def _version(
    plugin: Plugin,
    *,
    version_number: str = "1.0.0",
    released_at: datetime | None = None,
    **kwargs: object,
) -> PluginVersion:
    defaults: dict[str, object] = {
        "organization_id": plugin.organization_id,
        "plugin_id": plugin.id,
        "version_number": version_number,
        "released_at": released_at or utcnow(),
    }
    defaults.update(kwargs)
    return PluginVersion(**defaults)


def _publisher(organization_id: uuid.UUID, *, slug: str = "publisher", **kwargs: object) -> PluginPublisher:
    defaults: dict[str, object] = {
        "organization_id": organization_id,
        "slug": slug,
        "display_name": "Test Publisher",
    }
    defaults.update(kwargs)
    return PluginPublisher(**defaults)


class TestPluginRepository:
    async def test_create_and_require_by_id_round_trip(
        self, plugins_repo: PluginRepository, organization_id: uuid.UUID
    ) -> None:
        created = await plugins_repo.create(_plugin(organization_id, slug="roundtrip"))
        fetched = await plugins_repo.require_by_id(created.id)
        assert fetched.id == created.id
        assert fetched.slug == "roundtrip"

    async def test_require_in_org_hit(
        self, plugins_repo: PluginRepository, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="alpha"))
        found = await plugins_repo.require_in_org(organization_id, plugin.id)
        assert found.id == plugin.id

    async def test_require_in_org_miss_unknown_id(
        self, plugins_repo: PluginRepository, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await plugins_repo.require_in_org(organization_id, uuid.uuid4())

    async def test_require_in_org_miss_wrong_org(
        self, plugins_repo: PluginRepository, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="alpha"))
        with pytest.raises(NotFoundError):
            await plugins_repo.require_in_org(uuid.uuid4(), plugin.id)

    async def test_get_by_slug_hit(
        self, plugins_repo: PluginRepository, organization_id: uuid.UUID
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="alpha"))
        found = await plugins_repo.get_by_slug(organization_id, "alpha")
        assert found is not None
        assert found.id == plugin.id

    async def test_get_by_slug_miss(
        self, plugins_repo: PluginRepository, organization_id: uuid.UUID
    ) -> None:
        assert await plugins_repo.get_by_slug(organization_id, "nonexistent") is None

    async def test_get_by_slug_miss_wrong_org(
        self, plugins_repo: PluginRepository, organization_id: uuid.UUID
    ) -> None:
        await plugins_repo.create(_plugin(organization_id, slug="alpha"))
        assert await plugins_repo.get_by_slug(uuid.uuid4(), "alpha") is None

    async def test_list_for_org_category_and_status_filters(
        self, plugins_repo: PluginRepository, organization_id: uuid.UUID
    ) -> None:
        automation_published = await plugins_repo.create(
            _plugin(
                organization_id,
                slug="a",
                category=PluginCategory.AUTOMATION,
                status=PluginLifecycleStatus.PUBLISHED,
            )
        )
        security_registered = await plugins_repo.create(
            _plugin(
                organization_id,
                slug="b",
                category=PluginCategory.SECURITY,
                status=PluginLifecycleStatus.REGISTERED,
            )
        )
        automation_registered = await plugins_repo.create(
            _plugin(
                organization_id,
                slug="c",
                category=PluginCategory.AUTOMATION,
                status=PluginLifecycleStatus.REGISTERED,
            )
        )

        by_category = await plugins_repo.list_for_org(
            organization_id, category=PluginCategory.AUTOMATION
        )
        assert {p.id for p in by_category} == {automation_published.id, automation_registered.id}

        by_status = await plugins_repo.list_for_org(
            organization_id, status=PluginLifecycleStatus.REGISTERED
        )
        assert {p.id for p in by_status} == {security_registered.id, automation_registered.id}

        both = await plugins_repo.list_for_org(
            organization_id,
            category=PluginCategory.AUTOMATION,
            status=PluginLifecycleStatus.REGISTERED,
        )
        assert [p.id for p in both] == [automation_registered.id]

    async def test_list_for_org_pagination(
        self, plugins_repo: PluginRepository, organization_id: uuid.UUID
    ) -> None:
        for i in range(5):
            await plugins_repo.create(
                _plugin(organization_id, slug=f"page-{i}", created_at=ago((5 - i) * 10))
            )

        page1 = await plugins_repo.list_for_org(organization_id, limit=2, offset=0)
        page2 = await plugins_repo.list_for_org(organization_id, limit=2, offset=2)
        remainder = await plugins_repo.list_for_org(organization_id, limit=2, offset=4)

        assert [p.slug for p in page1] == ["page-4", "page-3"]
        assert [p.slug for p in page2] == ["page-2", "page-1"]
        assert [p.slug for p in remainder] == ["page-0"]

    async def test_list_for_org_empty(
        self, plugins_repo: PluginRepository, organization_id: uuid.UUID
    ) -> None:
        assert await plugins_repo.list_for_org(organization_id) == []

    async def test_list_by_publisher(
        self,
        plugins_repo: PluginRepository,
        publishers_repo: PluginPublisherRepository,
        organization_id: uuid.UUID,
    ) -> None:
        publisher = await publishers_repo.create(_publisher(organization_id, slug="pub-a"))
        other_publisher = await publishers_repo.create(_publisher(organization_id, slug="pub-b"))
        matching = await plugins_repo.create(
            _plugin(organization_id, slug="p1", publisher_id=publisher.id)
        )
        await plugins_repo.create(
            _plugin(organization_id, slug="p2", publisher_id=other_publisher.id)
        )
        await plugins_repo.create(_plugin(organization_id, slug="p3"))

        found = await plugins_repo.list_by_publisher(publisher.id)
        assert [p.id for p in found] == [matching.id]

    async def test_list_by_publisher_empty(self, plugins_repo: PluginRepository) -> None:
        assert await plugins_repo.list_by_publisher(uuid.uuid4()) == []


class TestPluginVersionRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="v-round"))
        created = await versions_repo.create(_version(plugin, version_number="1.0.0"))
        fetched = await versions_repo.require_by_id(created.id)
        assert fetched.id == created.id
        assert fetched.version_number == "1.0.0"

    async def test_list_for_plugin_ordering_newest_first(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="v-order"))
        oldest = await versions_repo.create(
            _version(plugin, version_number="1.0.0", released_at=ago(300), is_current=False)
        )
        newest = await versions_repo.create(
            _version(plugin, version_number="1.2.0", released_at=ago(10), is_current=True)
        )
        middle = await versions_repo.create(
            _version(plugin, version_number="1.1.0", released_at=ago(150), is_current=False)
        )

        versions = await versions_repo.list_for_plugin(plugin.id)
        assert [v.id for v in versions] == [newest.id, middle.id, oldest.id]

    async def test_list_for_plugin_empty(self, versions_repo: PluginVersionRepository) -> None:
        assert await versions_repo.list_for_plugin(uuid.uuid4()) == []

    async def test_get_current_hit(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="v-current"))
        await versions_repo.create(_version(plugin, version_number="1.0.0", is_current=False))
        current = await versions_repo.create(
            _version(plugin, version_number="2.0.0", is_current=True)
        )

        found = await versions_repo.get_current(plugin.id)
        assert found is not None
        assert found.id == current.id

    async def test_get_current_miss(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="v-nocurrent"))
        await versions_repo.create(_version(plugin, version_number="1.0.0", is_current=False))

        assert await versions_repo.get_current(plugin.id) is None

    async def test_get_by_version_number_hit(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="v-num"))
        version = await versions_repo.create(_version(plugin, version_number="3.1.4"))

        found = await versions_repo.get_by_version_number(plugin.id, "3.1.4")
        assert found is not None
        assert found.id == version.id

    async def test_get_by_version_number_miss(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="v-nonum"))
        await versions_repo.create(_version(plugin, version_number="1.0.0"))

        assert await versions_repo.get_by_version_number(plugin.id, "9.9.9") is None
