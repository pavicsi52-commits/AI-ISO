"""MarketplaceService: `slugify`, built-in catalog seeding, publishing,
compatibility checks, and install/rating bookkeeping.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import ConnectorCategory, MarketplaceStatus
from app.services.marketplace import _BUILTIN_CONNECTORS, MarketplaceService, slugify

# No module-level `pytestmark = pytest.mark.asyncio` here -- `asyncio_mode
# = "auto"` in pyproject.toml already covers every `async def test_*`
# without it, and applying it blanket would wrongly tag `TestSlugify`'s
# own plain sync tests too (pytest-asyncio then refuses to run a
# `@pytest.mark.asyncio`-tagged test that isn't a coroutine function).


class TestSlugify:
    def test_replaces_spaces_with_underscores(self) -> None:
        assert slugify("VMware vCenter") == "vmware_vcenter"

    def test_lowercases(self) -> None:
        assert slugify("AWS") == "aws"

    def test_collapses_special_characters_to_a_single_underscore(self) -> None:
        assert slugify("EtherNet/IP") == "ethernet_ip"

    def test_has_no_leading_or_trailing_underscore(self) -> None:
        assert slugify("  Weird   Name!! ") == "weird_name"

    def test_collapses_runs_of_punctuation(self) -> None:
        assert slugify("A---B..C") == "a_b_c"

    def test_single_word_is_unchanged_but_lowercased(self) -> None:
        assert slugify("Kubernetes") == "kubernetes"


class TestSeedBuiltinCatalog:
    async def test_creates_one_entry_per_builtin_connector(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        expected = sum(len(names) for names in _BUILTIN_CONNECTORS.values())
        # docs/058's own "BUILT-IN CONNECTORS" list, roughly 80 wide across
        # 12 named categories (Networking/Storage/Security/Business
        # Applications are named categories with no built-in entries here --
        # see `_BUILTIN_CONNECTORS`'s own docstring).
        assert expected >= 70
        assert len(_BUILTIN_CONNECTORS) == 12

        created = await marketplace_service.seed_builtin_catalog(organization_id)
        assert created == expected

        rows = await marketplace_service.list_for_org(organization_id, limit=1000)
        assert len(rows) == expected

    async def test_every_seeded_entry_is_built_in_and_published(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        await marketplace_service.seed_builtin_catalog(organization_id)
        rows = await marketplace_service.list_for_org(organization_id, limit=1000)
        assert rows  # sanity: the seed actually ran
        assert all(row.built_in is True for row in rows)
        assert all(row.status == MarketplaceStatus.PUBLISHED for row in rows)

    async def test_covers_every_named_category(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        await marketplace_service.seed_builtin_catalog(organization_id)
        rows = await marketplace_service.list_for_org(organization_id, limit=1000)
        found_categories = {row.category for row in rows}
        assert found_categories == set(_BUILTIN_CONNECTORS.keys())

    async def test_second_call_is_idempotent_and_creates_nothing(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        first = await marketplace_service.seed_builtin_catalog(organization_id)
        second = await marketplace_service.seed_builtin_catalog(organization_id)
        assert second == 0
        rows = await marketplace_service.list_for_org(organization_id, limit=1000)
        assert len(rows) == first

    async def test_is_scoped_per_organization(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        other_org = uuid4()
        await marketplace_service.seed_builtin_catalog(organization_id)
        created_for_other = await marketplace_service.seed_builtin_catalog(other_org)
        expected = sum(len(names) for names in _BUILTIN_CONNECTORS.values())
        assert created_for_other == expected


class TestPublish:
    async def test_publish_creates_a_published_entry(
        self, marketplace_service: MarketplaceService, organization_id, publisher
    ) -> None:
        created = await marketplace_service.publish(
            organization_id,
            slug="acme-widget",
            name="Acme Widget",
            category=ConnectorCategory.CUSTOM,
            version_number="2.1.0",
        )
        assert created.slug == "acme-widget"
        assert created.status == MarketplaceStatus.PUBLISHED
        assert created.built_in is False
        assert created.latest_version_number == "2.1.0"
        assert "MarketplaceUpdated" in publisher.names

    async def test_publish_raises_when_slug_already_exists(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        await marketplace_service.publish(
            organization_id, slug="dup-slug", name="First", category=ConnectorCategory.CUSTOM
        )
        with pytest.raises(ValidationError):
            await marketplace_service.publish(
                organization_id, slug="dup-slug", name="Second", category=ConnectorCategory.CUSTOM
            )

    async def test_publish_raises_when_a_dependency_is_not_published(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await marketplace_service.publish(
                organization_id,
                slug="needs-missing-dep",
                name="Needs missing dep",
                category=ConnectorCategory.CUSTOM,
                dependencies=["does-not-exist"],
            )

    async def test_publish_succeeds_with_an_already_published_dependency(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        await marketplace_service.publish(
            organization_id, slug="base-lib", name="Base Lib", category=ConnectorCategory.CUSTOM
        )
        created = await marketplace_service.publish(
            organization_id,
            slug="depends-on-base",
            name="Depends On Base",
            category=ConnectorCategory.CUSTOM,
            dependencies=["base-lib"],
        )
        assert created.dependencies == ["base-lib"]

    async def test_publish_failure_does_not_persist_a_row(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await marketplace_service.publish(
                organization_id,
                slug="orphan",
                name="Orphan",
                category=ConnectorCategory.CUSTOM,
                dependencies=["missing"],
            )
        rows = await marketplace_service.list_for_org(organization_id)
        assert rows == []

    async def test_publish_raises_once_the_same_slug_has_been_seeded_as_a_builtin(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        # `publish` and `seed_builtin_catalog` share `get_by_slug`'s own
        # per-organization uniqueness check -- once an org's catalog has
        # been seeded, publishing a connector under a built-in's own slug
        # collides exactly like any other duplicate slug.
        await marketplace_service.seed_builtin_catalog(organization_id)
        with pytest.raises(ValidationError):
            await marketplace_service.publish(
                organization_id, slug="aws", name="My Own AWS Fork", category=ConnectorCategory.CLOUD
            )


class TestGetAndList:
    async def test_get_returns_the_entry(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        created = await marketplace_service.publish(
            organization_id, slug="gettable", name="Gettable", category=ConnectorCategory.CUSTOM
        )
        found = await marketplace_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_get_raises_not_found_for_a_missing_entry(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await marketplace_service.get(organization_id, uuid4())

    async def test_get_is_scoped_to_its_organization(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        created = await marketplace_service.publish(
            organization_id, slug="scoped", name="Scoped", category=ConnectorCategory.CUSTOM
        )
        with pytest.raises(NotFoundError):
            await marketplace_service.get(uuid4(), created.id)

    async def test_list_filters_by_category(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        cloud_entry = await marketplace_service.publish(
            organization_id, slug="cloud-one", name="Cloud One", category=ConnectorCategory.CLOUD
        )
        await marketplace_service.publish(
            organization_id, slug="custom-one", name="Custom One", category=ConnectorCategory.CUSTOM
        )
        found = await marketplace_service.list_for_org(
            organization_id, category=ConnectorCategory.CLOUD
        )
        ids = {row.id for row in found}
        assert cloud_entry.id in ids
        assert len(found) == 1

    async def test_list_is_scoped_per_organization(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        await marketplace_service.publish(
            organization_id, slug="mine", name="Mine", category=ConnectorCategory.CUSTOM
        )
        found = await marketplace_service.list_for_org(uuid4())
        assert found == []


class TestCheckCompatible:
    async def test_true_when_version_satisfies_the_constraint(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        entry = await marketplace_service.publish(
            organization_id,
            slug="versioned",
            name="Versioned",
            category=ConnectorCategory.CUSTOM,
            version_number="1.5.0",
        )
        assert marketplace_service.check_compatible(entry, constraint=">=1.0.0,<2.0.0") is True

    async def test_false_when_version_is_outside_the_constraint(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        entry = await marketplace_service.publish(
            organization_id,
            slug="versioned-2",
            name="Versioned 2",
            category=ConnectorCategory.CUSTOM,
            version_number="1.5.0",
        )
        assert marketplace_service.check_compatible(entry, constraint=">=2.0.0") is False

    async def test_true_for_an_unconstrained_wildcard(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        entry = await marketplace_service.publish(
            organization_id,
            slug="versioned-3",
            name="Versioned 3",
            category=ConnectorCategory.CUSTOM,
            version_number="0.0.1",
        )
        assert marketplace_service.check_compatible(entry, constraint="*") is True


class TestRecordInstall:
    async def test_bumps_install_count(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        entry = await marketplace_service.publish(
            organization_id,
            slug="installable",
            name="Installable",
            category=ConnectorCategory.CUSTOM,
        )
        assert entry.install_count == 0
        updated = await marketplace_service.record_install(organization_id, entry.id)
        assert updated.install_count == 1
        updated_again = await marketplace_service.record_install(organization_id, entry.id)
        assert updated_again.install_count == 2

    async def test_raises_not_found_for_a_missing_entry(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await marketplace_service.record_install(organization_id, uuid4())


class TestRate:
    async def test_accumulates_rating_total_and_count(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        entry = await marketplace_service.publish(
            organization_id, slug="rateable", name="Rateable", category=ConnectorCategory.CUSTOM
        )
        await marketplace_service.rate(organization_id, entry.id, rating=4.0)
        rated = await marketplace_service.rate(organization_id, entry.id, rating=5.0)
        assert rated.rating_total == 9.0
        assert rated.rating_count == 2

    async def test_raises_for_rating_below_the_minimum(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        entry = await marketplace_service.publish(
            organization_id, slug="too-low", name="Too Low", category=ConnectorCategory.CUSTOM
        )
        with pytest.raises(ValidationError):
            await marketplace_service.rate(organization_id, entry.id, rating=0.5)

    async def test_raises_for_rating_above_the_maximum(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        entry = await marketplace_service.publish(
            organization_id, slug="too-high", name="Too High", category=ConnectorCategory.CUSTOM
        )
        with pytest.raises(ValidationError):
            await marketplace_service.rate(organization_id, entry.id, rating=5.5)

    async def test_accepts_the_lower_boundary(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        entry = await marketplace_service.publish(
            organization_id,
            slug="lower-boundary",
            name="Lower Boundary",
            category=ConnectorCategory.CUSTOM,
        )
        rated = await marketplace_service.rate(organization_id, entry.id, rating=1.0)
        assert rated.rating_count == 1
        assert rated.rating_total == 1.0

    async def test_accepts_the_upper_boundary(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        entry = await marketplace_service.publish(
            organization_id,
            slug="upper-boundary",
            name="Upper Boundary",
            category=ConnectorCategory.CUSTOM,
        )
        rated = await marketplace_service.rate(organization_id, entry.id, rating=5.0)
        assert rated.rating_count == 1
        assert rated.rating_total == 5.0

    async def test_invalid_rating_does_not_mutate_the_entry(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        entry = await marketplace_service.publish(
            organization_id, slug="unchanged", name="Unchanged", category=ConnectorCategory.CUSTOM
        )
        with pytest.raises(ValidationError):
            await marketplace_service.rate(organization_id, entry.id, rating=99.0)
        fetched = await marketplace_service.get(organization_id, entry.id)
        assert fetched.rating_count == 0
        assert fetched.rating_total == 0.0

    async def test_raises_not_found_for_a_missing_entry(
        self, marketplace_service: MarketplaceService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await marketplace_service.rate(organization_id, uuid4(), rating=3.0)
