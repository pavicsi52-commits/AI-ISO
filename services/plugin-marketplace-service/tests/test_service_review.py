"""Tests for ``app.services.review.PluginReviewService``."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.validation import ValidationError

from app.models.enums import ReviewStatus
from app.services.review import PluginReviewService
from tests.conftest import MakePluginFn


async def test_submit_happy_path_creates_published_review_and_rating(
    review_service: PluginReviewService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="review-plugin")

    review = await review_service.submit(
        organization_id,
        plugin.id,
        reviewer_id="reviewer-1",
        rating=4,
        title="Pretty good",
        body="Does what it says.",
        installed_version_number="1.0.0",
        verified_install=True,
    )

    assert review.status == ReviewStatus.PUBLISHED
    assert review.rating == 4
    assert review.title == "Pretty good"
    assert review.body == "Does what it says."
    assert review.verified_install is True

    rating = await review_service.get_rating(plugin.id)
    assert rating is not None
    assert rating.average_rating == 4.0
    assert rating.review_count == 1
    assert rating.rating_4_count == 1


async def test_submit_rating_outside_range_raises(
    review_service: PluginReviewService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="review-plugin-bad-rating")

    with pytest.raises(ValidationError):
        await review_service.submit(
            organization_id, plugin.id, reviewer_id="reviewer-1", rating=0
        )

    with pytest.raises(ValidationError):
        await review_service.submit(
            organization_id, plugin.id, reviewer_id="reviewer-1", rating=6
        )


async def test_submit_again_updates_existing_review_not_duplicate(
    review_service: PluginReviewService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="review-plugin-update")

    first = await review_service.submit(
        organization_id, plugin.id, reviewer_id="same-reviewer", rating=2, body="meh"
    )
    second = await review_service.submit(
        organization_id, plugin.id, reviewer_id="same-reviewer", rating=5, body="actually great"
    )

    assert first.id == second.id
    assert second.rating == 5
    assert second.body == "actually great"

    published = await review_service.list_published(plugin.id)
    assert len(published) == 1

    rating = await review_service.get_rating(plugin.id)
    assert rating is not None
    assert rating.review_count == 1
    assert rating.average_rating == 5.0


async def test_flag_sets_flagged_state(
    review_service: PluginReviewService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="review-plugin-flag")
    review = await review_service.submit(
        organization_id, plugin.id, reviewer_id="flagged-reviewer", rating=1, body="spam"
    )

    flagged = await review_service.flag(review.id, reason="spam content", moderated_by="mod-1")

    assert flagged.status == ReviewStatus.FLAGGED
    assert flagged.flagged_reason == "spam content"
    assert flagged.moderated_by == "mod-1"
    assert flagged.moderated_at is not None


async def test_remove_sets_removed_and_recomputes_rating(
    review_service: PluginReviewService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="review-plugin-remove")
    keep = await review_service.submit(
        organization_id, plugin.id, reviewer_id="keeper", rating=5
    )
    remove_me = await review_service.submit(
        organization_id, plugin.id, reviewer_id="removed-reviewer", rating=1
    )

    removed = await review_service.remove(remove_me.id, moderated_by="mod-1")

    assert removed.status == ReviewStatus.REMOVED
    assert removed.moderated_by == "mod-1"
    assert removed.moderated_at is not None

    rating = await review_service.get_rating(plugin.id)
    assert rating is not None
    assert rating.review_count == 1
    assert rating.average_rating == 5.0
    assert rating.rating_5_count == 1
    assert rating.rating_1_count == 0

    published = await review_service.list_published(plugin.id)
    assert {r.id for r in published} == {keep.id}


async def test_respond_sets_publisher_response(
    review_service: PluginReviewService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="review-plugin-respond")
    review = await review_service.submit(
        organization_id, plugin.id, reviewer_id="responded-to", rating=3
    )

    responded = await review_service.respond(review.id, response="Thanks for the feedback!")

    assert responded.publisher_response == "Thanks for the feedback!"
    assert responded.publisher_responded_at is not None


async def test_list_published_excludes_flagged_and_removed(
    review_service: PluginReviewService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="review-plugin-list")
    published = await review_service.submit(
        organization_id, plugin.id, reviewer_id="published-reviewer", rating=5
    )
    to_flag = await review_service.submit(
        organization_id, plugin.id, reviewer_id="flag-reviewer", rating=2
    )
    to_remove = await review_service.submit(
        organization_id, plugin.id, reviewer_id="remove-reviewer", rating=1
    )
    await review_service.flag(to_flag.id, reason="bad")
    await review_service.remove(to_remove.id)

    result = await review_service.list_published(plugin.id)
    assert {r.id for r in result} == {published.id}


async def test_get_rating_returns_none_before_any_review(
    review_service: PluginReviewService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="review-plugin-no-reviews")

    assert await review_service.get_rating(plugin.id) is None


async def test_recompute_rating_math_correctness(
    review_service: PluginReviewService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="review-plugin-math")
    ratings = [5, 5, 3, 1]
    for index, rating in enumerate(ratings):
        await review_service.submit(
            organization_id, plugin.id, reviewer_id=f"reviewer-{index}", rating=rating
        )

    aggregate = await review_service.get_rating(plugin.id)
    assert aggregate is not None
    assert aggregate.review_count == 4
    assert aggregate.average_rating == pytest.approx(3.5)
    assert aggregate.rating_1_count == 1
    assert aggregate.rating_2_count == 0
    assert aggregate.rating_3_count == 1
    assert aggregate.rating_4_count == 0
    assert aggregate.rating_5_count == 2
    assert aggregate.recalculated_at is not None


async def test_list_pending_moderation_only_returns_flagged(
    review_service: PluginReviewService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="review-plugin-moderation")
    normal = await review_service.submit(
        organization_id, plugin.id, reviewer_id="normal-reviewer", rating=4
    )
    to_flag = await review_service.submit(
        organization_id, plugin.id, reviewer_id="flagged-for-mod", rating=1
    )
    to_remove = await review_service.submit(
        organization_id, plugin.id, reviewer_id="removed-not-flagged", rating=2
    )
    await review_service.flag(to_flag.id, reason="abusive")
    await review_service.remove(to_remove.id)

    pending = await review_service.list_pending_moderation()
    pending_ids = {r.id for r in pending}
    assert to_flag.id in pending_ids
    assert normal.id not in pending_ids
    assert to_remove.id not in pending_ids
