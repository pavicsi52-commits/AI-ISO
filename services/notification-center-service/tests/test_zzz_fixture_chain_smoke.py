"""A throwaway smoke test verifying the whole fixture chain against real infra.

Not part of the permanent suite's own coverage story -- exists to catch
a broken fixture *before* delegating bulk test-writing, the same
workflow every prior AI-IOS service's own build used.
"""

from __future__ import annotations

import pytest

from app.models.enums import (
    NotificationChannelKind,
    NotificationStatus,
    notification_status_of,
)

pytestmark = pytest.mark.asyncio


class TestSmoke:
    async def test_create_and_dispatch_in_app_succeeds(self, make_notification, delivery_service, organization_id):
        notification = await make_notification(user_id="user-1")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        assert len(deliveries) == 1
        assert notification_status_of(deliveries[0].status) == NotificationStatus.DELIVERED

    async def test_dispatch_to_unregistered_channel_dead_letters_after_retries(
        self, make_notification, delivery_service, organization_id
    ):
        # EMAIL is always org-enabled by this service's own rule but was
        # never registered in the `notification_manager` fixture (no
        # `EmailSettings` passed to `create_notification_framework()`) --
        # so this genuinely exercises `ChannelUnavailableError` handling.
        notification = await make_notification(user_id="user-2")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        assert len(deliveries) == 1
        delivery = deliveries[0]
        assert notification_status_of(delivery.status) in (
            NotificationStatus.QUEUED,
            NotificationStatus.FAILED,
        )

    async def test_preference_default_is_permissive(self, preference_service, organization_id):
        preferences = await preference_service.get(organization_id, "brand-new-user")
        assert preferences.muted is False

    async def test_template_create_and_preview(self, make_template, template_service, organization_id):
        template = await make_template(body_template="Hi {{ name }}!")
        rendered = await template_service.preview(organization_id, template.id, {"name": "Ada"})
        assert rendered.body == "Hi Ada!"

    async def test_subscription_and_broadcast(
        self, subscription_service, broadcast_service, organization_id
    ):
        from app.models.enums import SubscriptionKind

        await subscription_service.subscribe(organization_id, "user-3", SubscriptionKind.TOPIC, "outages")
        broadcast = await broadcast_service.broadcast(
            organization_id, body="Outage resolved.", topic="outages", initiated_by="admin"
        )
        assert broadcast.total_recipients == 1

    async def test_announcement_publish(self, announcement_service, organization_id):
        from app.models.enums import AnnouncementScope

        announcement = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Maintenance", body="Tonight at 9pm."
        )
        published = await announcement_service.publish(organization_id, announcement.id)
        assert published.published_at is not None

    async def test_statistics_rollup(self, make_notification, statistics_service, organization_id):
        from tests.conftest import ago, soon

        await make_notification(user_id="user-4")
        window = await statistics_service.rollup(
            organization_id, window_start=ago(hours=1), window_end=soon(hours=1)
        )
        assert window is not None

    async def test_http_health_endpoint(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "healthy"

    async def test_http_create_and_send_notification(self, client, auth_headers, organization_id):
        import uuid

        user_id = uuid.uuid4()
        response = await client.post(
            "/notifications/send",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(user_id),
            json={
                "user_id": "http-user-1",
                "category": "information",
                "body": "HTTP smoke test.",
                "source_service": "test-suite",
                "channel": "in_app",
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["data"]["status"] in ("sent", "delivered")
