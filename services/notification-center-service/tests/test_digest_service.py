"""DigestService: bundling a user's own unread notifications into one digest.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import (
    DigestFrequency,
    NotificationCategory,
    NotificationPriority,
    NotificationStatus,
    notification_status_of,
)
from app.services.digest import DigestService

pytestmark = pytest.mark.asyncio


class TestBuildAndSend:
    async def test_returns_none_when_the_users_digest_frequency_is_none(
        self, digest_service: DigestService, make_notification, organization_id
    ) -> None:
        # DigestFrequency.NONE is the default preference -- calling
        # make_preference is required to opt a user into any digest at all.
        await make_notification(user_id="user-no-digest")
        result = await digest_service.build_and_send(
            organization_id, "user-no-digest", now=datetime.now(UTC)
        )
        assert result is None

    async def test_returns_none_when_nothing_is_unread_in_the_window(
        self, digest_service: DigestService, make_preference, organization_id
    ) -> None:
        await make_preference(user_id="user-empty", digest_frequency=DigestFrequency.HOURLY)
        result = await digest_service.build_and_send(
            organization_id, "user-empty", now=datetime.now(UTC)
        )
        assert result is None

    async def test_returns_none_when_only_read_and_digest_category_notifications_exist(
        self,
        digest_service: DigestService,
        make_preference,
        make_notification,
        notification_service,
        organization_id,
    ) -> None:
        await make_preference(user_id="user-filtered", digest_frequency=DigestFrequency.HOURLY)
        already_read = await make_notification(user_id="user-filtered", body="Already read.")
        await notification_service.mark_read(organization_id, already_read.id)
        await make_notification(
            user_id="user-filtered", category=NotificationCategory.DIGEST, body="A prior digest."
        )

        result = await digest_service.build_and_send(
            organization_id, "user-filtered", now=datetime.now(UTC)
        )
        assert result is None

    async def test_builds_one_digest_from_genuinely_unread_non_digest_notifications(
        self,
        digest_service: DigestService,
        make_preference,
        make_notification,
        notification_service,
        organization_id,
    ) -> None:
        await make_preference(user_id="user-digest", digest_frequency=DigestFrequency.HOURLY)
        already_read = await make_notification(
            user_id="user-digest", body="Excluded: already read."
        )
        await notification_service.mark_read(organization_id, already_read.id)
        await make_notification(
            user_id="user-digest",
            category=NotificationCategory.DIGEST,
            body="Excluded: a prior digest.",
        )
        await make_notification(user_id="user-digest", body="Included: genuinely unread.")

        result = await digest_service.build_and_send(
            organization_id, "user-digest", now=datetime.now(UTC)
        )

        assert result is not None
        assert result.category == NotificationCategory.DIGEST
        assert result.priority == NotificationPriority.LOW
        assert "Included: genuinely unread." in result.body
        assert "Excluded: already read." not in result.body
        assert "Excluded: a prior digest." not in result.body

    async def test_digest_subject_names_the_frequency(
        self, digest_service: DigestService, make_preference, make_notification, organization_id
    ) -> None:
        await make_preference(user_id="user-subject", digest_frequency=DigestFrequency.DAILY)
        await make_notification(user_id="user-subject", body="News.")
        result = await digest_service.build_and_send(
            organization_id, "user-subject", now=datetime.now(UTC)
        )
        assert result is not None
        assert result.subject == "Your daily digest"

    async def test_dispatches_the_digest_notification(
        self,
        digest_service: DigestService,
        make_preference,
        make_notification,
        notification_service,
        organization_id,
    ) -> None:
        await make_preference(user_id="user-dispatch", digest_frequency=DigestFrequency.HOURLY)
        await make_notification(user_id="user-dispatch", body="News.")
        result = await digest_service.build_and_send(
            organization_id, "user-dispatch", now=datetime.now(UTC)
        )
        assert result is not None
        reloaded = await notification_service.get(organization_id, result.id)
        # The default preferred_channels the make_preference fixture sets
        # is [IN_APP], which always succeeds -- a real dispatch, not a stub.
        assert notification_status_of(reloaded.status) == NotificationStatus.DELIVERED

    async def test_excludes_notifications_created_before_the_lookback_window(
        self, digest_service: DigestService, make_preference, make_notification, organization_id
    ) -> None:
        await make_preference(user_id="user-old", digest_frequency=DigestFrequency.HOURLY)
        await make_notification(user_id="user-old", body="Old news.")
        far_future = datetime.now(UTC) + timedelta(hours=5)
        result = await digest_service.build_and_send(organization_id, "user-old", now=far_future)
        assert result is None

    async def test_every_non_none_frequency_can_build_a_digest(
        self, digest_service: DigestService, make_preference, make_notification, organization_id
    ) -> None:
        for index, frequency in enumerate(
            (
                DigestFrequency.HOURLY,
                DigestFrequency.DAILY,
                DigestFrequency.WEEKLY,
                DigestFrequency.MONTHLY,
            )
        ):
            user_id = f"user-freq-{index}"
            await make_preference(user_id=user_id, digest_frequency=frequency)
            await make_notification(user_id=user_id, body=f"News for {frequency.value}.")
            result = await digest_service.build_and_send(
                organization_id, user_id, now=datetime.now(UTC)
            )
            assert result is not None, f"expected a digest for {frequency}"
            assert result.category == NotificationCategory.DIGEST

    async def test_groups_unread_notifications_of_different_categories(
        self, digest_service: DigestService, make_preference, make_notification, organization_id
    ) -> None:
        await make_preference(user_id="user-groups", digest_frequency=DigestFrequency.HOURLY)
        await make_notification(
            user_id="user-groups", category=NotificationCategory.ALERT, body="An alert."
        )
        await make_notification(
            user_id="user-groups", category=NotificationCategory.INFORMATION, body="An update."
        )
        result = await digest_service.build_and_send(
            organization_id, "user-groups", now=datetime.now(UTC)
        )
        assert result is not None
        assert "An alert." in result.body
        assert "An update." in result.body
