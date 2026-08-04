"""HTTP tests for /notifications/dead-letters -- listing and manual retry.

``GET`` (list) needs no auth; ``POST .../retry`` declares a
``caller: CurrentUserId`` parameter and needs ``Authorization`` headers.

Dead letters are not reachable end-to-end over HTTP in a deterministic
way (reaching one for real means exhausting every retry, which is time-
driven) -- so each test seeds a dead-lettered delivery directly through
the repository layer, on the same session the ``client`` fixture's app
uses, then exercises the route against that seeded row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import HTTP_NOT_FOUND, HTTP_OK, HTTP_UNAUTHORIZED

from app.models.delivery import NotificationDelivery
from app.models.notification import Notification
from app.models.retry import NotificationDeadLetter
from app.repositories.delivery import NotificationDeliveryRepository
from app.repositories.retry import NotificationDeadLetterRepository

pytestmark = pytest.mark.asyncio


async def _seed_dead_letter(
    db_session: AsyncSession,
    organization_id: uuid.UUID,
    notification: Notification,
    *,
    channel: str = "in_app",
) -> NotificationDeadLetter:
    now = datetime.now(UTC)
    delivery = await NotificationDeliveryRepository(db_session).create(
        NotificationDelivery(
            organization_id=organization_id,
            notification_id=notification.id,
            channel=channel,
            status="failed",
            queued_at=now,
            failed_at=now,
            attempts_used=3,
        )
    )
    return await NotificationDeadLetterRepository(db_session).create(
        NotificationDeadLetter(
            organization_id=organization_id,
            notification_id=notification.id,
            delivery_id=delivery.id,
            channel=channel,
            attempts=3,
            last_error="Simulated exhausted retries.",
            dead_lettered_at=now,
        )
    )


class TestList:
    async def test_list_is_empty_before_any_dead_letter(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/notifications/dead-letters", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_the_seeded_dead_letter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
        make_notification,
    ) -> None:
        notification = await make_notification()
        dead_letter = await _seed_dead_letter(db_session, organization_id, notification)
        resp = await client.get(
            "/notifications/dead-letters", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {row["id"] for row in resp.json()["data"]}
        assert str(dead_letter.id) in ids

    async def test_list_filters_by_resolved(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
        make_notification,
    ) -> None:
        notification = await make_notification()
        dead_letter = await _seed_dead_letter(db_session, organization_id, notification)
        unresolved = await client.get(
            "/notifications/dead-letters",
            params={"organization_id": str(organization_id), "resolved": "false"},
        )
        assert str(dead_letter.id) in {row["id"] for row in unresolved.json()["data"]}
        resolved = await client.get(
            "/notifications/dead-letters",
            params={"organization_id": str(organization_id), "resolved": "true"},
        )
        assert str(dead_letter.id) not in {row["id"] for row in resolved.json()["data"]}


class TestRetry:
    async def test_retry_requires_auth(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
        make_notification,
    ) -> None:
        notification = await make_notification()
        dead_letter = await _seed_dead_letter(db_session, organization_id, notification)
        resp = await client.post(
            f"/notifications/dead-letters/{dead_letter.id}/retry",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_retry_resolves_the_dead_letter_and_reattempts_delivery(
        self,
        client: AsyncClient,
        auth_headers,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
        make_notification,
    ) -> None:
        notification = await make_notification()
        dead_letter = await _seed_dead_letter(db_session, organization_id, notification, channel="in_app")
        resp = await client.post(
            f"/notifications/dead-letters/{dead_letter.id}/retry",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["channel"] == "in_app"
        # IN_APP is always registered by the real app's own lifespan, so
        # the retried attempt succeeds outright.
        assert data["status"] == "delivered"

        still_listed_as_resolved = await client.get(
            "/notifications/dead-letters",
            params={"organization_id": str(organization_id), "resolved": "true"},
        )
        ids = {row["id"] for row in still_listed_as_resolved.json()["data"]}
        assert str(dead_letter.id) in ids

    async def test_retry_returns_404_for_a_missing_dead_letter(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/notifications/dead-letters/{uuid.uuid4()}/retry",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND
