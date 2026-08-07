"""Repository tests for ``PluginReviewRepository``, ``PluginRatingRepository``,
and ``PluginPublisherRepository``.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import PluginCategory, PluginType, ReviewStatus
from app.models.plugin import Plugin
from app.models.publisher import PluginPublisher
from app.models.review import PluginRating, PluginReview
from app.repositories.plugin import PluginRepository
from app.repositories.publisher import PluginPublisherRepository
from app.repositories.review import PluginRatingRepository, PluginReviewRepository
from tests.conftest import ago


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


def _review(
    plugin: Plugin, *, reviewer_id: str = "reviewer-1", rating: int = 5, **kwargs: object
) -> PluginReview:
    defaults: dict[str, object] = {
        "organization_id": plugin.organization_id,
        "plugin_id": plugin.id,
        "reviewer_id": reviewer_id,
        "rating": rating,
    }
    defaults.update(kwargs)
    return PluginReview(**defaults)


def _rating_row(plugin: Plugin, **kwargs: object) -> PluginRating:
    defaults: dict[str, object] = {
        "organization_id": plugin.organization_id,
        "plugin_id": plugin.id,
    }
    defaults.update(kwargs)
    return PluginRating(**defaults)


def _publisher(
    organization_id: uuid.UUID, *, slug: str = "publisher", **kwargs: object
) -> PluginPublisher:
    defaults: dict[str, object] = {
        "organization_id": organization_id,
        "slug": slug,
        "display_name": "Test Publisher",
    }
    defaults.update(kwargs)
    return PluginPublisher(**defaults)


class TestPluginReviewRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        reviews_repo: PluginReviewRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rev-round"))
        created = await reviews_repo.create(_review(plugin))
        fetched = await reviews_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_list_published_for_plugin(
        self,
        plugins_repo: PluginRepository,
        reviews_repo: PluginReviewRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rev-published"))
        newer = await reviews_repo.create(
            _review(plugin, reviewer_id="r1", status=ReviewStatus.PUBLISHED, created_at=ago(10))
        )
        older = await reviews_repo.create(
            _review(plugin, reviewer_id="r2", status=ReviewStatus.PUBLISHED, created_at=ago(200))
        )
        await reviews_repo.create(_review(plugin, reviewer_id="r3", status=ReviewStatus.FLAGGED))

        found = await reviews_repo.list_published_for_plugin(plugin.id)
        assert [r.id for r in found] == [newer.id, older.id]

    async def test_list_published_for_plugin_pagination(
        self,
        plugins_repo: PluginRepository,
        reviews_repo: PluginReviewRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rev-page"))
        rows = [
            await reviews_repo.create(
                _review(plugin, reviewer_id=f"r{i}", created_at=ago((3 - i) * 20))
            )
            for i in range(3)
        ]

        page = await reviews_repo.list_published_for_plugin(plugin.id, limit=1, offset=1)
        assert len(page) == 1
        assert page[0].id == rows[1].id

    async def test_list_published_for_plugin_empty(
        self, reviews_repo: PluginReviewRepository
    ) -> None:
        assert await reviews_repo.list_published_for_plugin(uuid.uuid4()) == []

    async def test_list_all_for_plugin_includes_every_status(
        self,
        plugins_repo: PluginRepository,
        reviews_repo: PluginReviewRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rev-all"))
        published = await reviews_repo.create(
            _review(plugin, reviewer_id="r1", status=ReviewStatus.PUBLISHED)
        )
        flagged = await reviews_repo.create(
            _review(plugin, reviewer_id="r2", status=ReviewStatus.FLAGGED)
        )

        found = await reviews_repo.list_all_for_plugin(plugin.id)
        assert {r.id for r in found} == {published.id, flagged.id}

    async def test_list_all_for_plugin_empty(self, reviews_repo: PluginReviewRepository) -> None:
        assert await reviews_repo.list_all_for_plugin(uuid.uuid4()) == []

    async def test_get_by_reviewer_hit(
        self,
        plugins_repo: PluginRepository,
        reviews_repo: PluginReviewRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rev-reviewer"))
        review = await reviews_repo.create(_review(plugin, reviewer_id="alice"))

        found = await reviews_repo.get_by_reviewer(plugin.id, "alice")
        assert found is not None
        assert found.id == review.id

    async def test_get_by_reviewer_miss(
        self,
        plugins_repo: PluginRepository,
        reviews_repo: PluginReviewRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rev-noreviewer"))
        await reviews_repo.create(_review(plugin, reviewer_id="alice"))

        assert await reviews_repo.get_by_reviewer(plugin.id, "bob") is None

    async def test_list_pending_moderation(
        self,
        plugins_repo: PluginRepository,
        reviews_repo: PluginReviewRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rev-moderation"))
        older_flag = await reviews_repo.create(
            _review(plugin, reviewer_id="r1", status=ReviewStatus.FLAGGED, created_at=ago(200))
        )
        newer_flag = await reviews_repo.create(
            _review(plugin, reviewer_id="r2", status=ReviewStatus.FLAGGED, created_at=ago(10))
        )
        await reviews_repo.create(_review(plugin, reviewer_id="r3", status=ReviewStatus.PUBLISHED))

        found = await reviews_repo.list_pending_moderation()
        assert [r.id for r in found] == [older_flag.id, newer_flag.id]

    async def test_list_pending_moderation_empty(
        self,
        plugins_repo: PluginRepository,
        reviews_repo: PluginReviewRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rev-nomoderation"))
        await reviews_repo.create(_review(plugin, reviewer_id="r1", status=ReviewStatus.PUBLISHED))

        assert await reviews_repo.list_pending_moderation() == []


class TestPluginRatingRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        ratings_repo: PluginRatingRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rating-round"))
        created = await ratings_repo.create(
            _rating_row(plugin, average_rating=4.5, review_count=10)
        )
        fetched = await ratings_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_get_for_plugin_hit(
        self,
        plugins_repo: PluginRepository,
        ratings_repo: PluginRatingRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rating-hit"))
        rating = await ratings_repo.create(_rating_row(plugin, average_rating=3.2, review_count=5))

        found = await ratings_repo.get_for_plugin(plugin.id)
        assert found is not None
        assert found.id == rating.id

    async def test_get_for_plugin_miss(
        self,
        plugins_repo: PluginRepository,
        ratings_repo: PluginRatingRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rating-miss"))
        assert await ratings_repo.get_for_plugin(plugin.id) is None


class TestPluginPublisherRepository:
    async def test_create_and_require_by_id_round_trip(
        self, publishers_repo: PluginPublisherRepository, organization_id: uuid.UUID
    ) -> None:
        created = await publishers_repo.create(_publisher(organization_id, slug="pub-round"))
        fetched = await publishers_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_require_in_org_hit(
        self, publishers_repo: PluginPublisherRepository, organization_id: uuid.UUID
    ) -> None:
        publisher = await publishers_repo.create(_publisher(organization_id, slug="pub-hit"))
        found = await publishers_repo.require_in_org(organization_id, publisher.id)
        assert found.id == publisher.id

    async def test_require_in_org_miss_unknown_id(
        self, publishers_repo: PluginPublisherRepository, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await publishers_repo.require_in_org(organization_id, uuid.uuid4())

    async def test_require_in_org_miss_wrong_org(
        self, publishers_repo: PluginPublisherRepository, organization_id: uuid.UUID
    ) -> None:
        publisher = await publishers_repo.create(_publisher(organization_id, slug="pub-wrongorg"))
        with pytest.raises(NotFoundError):
            await publishers_repo.require_in_org(uuid.uuid4(), publisher.id)

    async def test_get_by_slug_hit(
        self, publishers_repo: PluginPublisherRepository, organization_id: uuid.UUID
    ) -> None:
        publisher = await publishers_repo.create(_publisher(organization_id, slug="pub-slug"))
        found = await publishers_repo.get_by_slug(organization_id, "pub-slug")
        assert found is not None
        assert found.id == publisher.id

    async def test_get_by_slug_miss(
        self, publishers_repo: PluginPublisherRepository, organization_id: uuid.UUID
    ) -> None:
        assert await publishers_repo.get_by_slug(organization_id, "nonexistent") is None

    async def test_get_by_slug_miss_wrong_org(
        self, publishers_repo: PluginPublisherRepository, organization_id: uuid.UUID
    ) -> None:
        await publishers_repo.create(_publisher(organization_id, slug="pub-cross"))
        assert await publishers_repo.get_by_slug(uuid.uuid4(), "pub-cross") is None

    async def test_list_for_org(
        self, publishers_repo: PluginPublisherRepository, organization_id: uuid.UUID
    ) -> None:
        other_org = uuid.uuid4()
        own_a = await publishers_repo.create(_publisher(organization_id, slug="own-a"))
        own_b = await publishers_repo.create(_publisher(organization_id, slug="own-b"))
        await publishers_repo.create(_publisher(other_org, slug="foreign"))

        found = await publishers_repo.list_for_org(organization_id)
        assert {p.id for p in found} == {own_a.id, own_b.id}

    async def test_list_for_org_empty(
        self, publishers_repo: PluginPublisherRepository, organization_id: uuid.UUID
    ) -> None:
        assert await publishers_repo.list_for_org(organization_id) == []
