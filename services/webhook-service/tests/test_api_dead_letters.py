"""``app/api/deliveries.py``'s ``dead_letters_router`` -- ``/webhooks/dead-letters``.

A deliberately separate router from ``/webhooks/deliveries`` (see that
module's own docstring for why) -- covered here rather than in
``test_api_deliveries.py`` to mirror that separation. Neither route here
takes a ``CurrentUserId`` dependency: both are read-only, consistent with
every other read-style route in this API.
"""

from __future__ import annotations

import uuid

from tests.conftest import FAKE_BACKEND_URL, HTTP_NOT_FOUND, HTTP_OK


async def _dead_letter(delivery_service, make_endpoint, make_event, organization_id):
    """Queue and deliver against a permanently-failing endpoint until it dead-letters."""
    endpoint = await make_endpoint(url=f"{FAKE_BACKEND_URL}/error", max_attempts=1)
    event = await make_event()
    delivery = await delivery_service.queue_direct(organization_id, event, endpoint_id=endpoint.id)
    outcome = await delivery_service.deliver(organization_id, delivery)
    assert outcome.delivery.status == "expired"
    return delivery, endpoint


class TestListDeadLettersEndpoint:
    async def test_lists_dead_lettered_deliveries_in_the_organization(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, endpoint = await _dead_letter(
            delivery_service, make_endpoint, make_event, organization_id
        )

        response = await client.get(
            "/webhooks/dead-letters", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        body = response.json()["data"]
        assert len(body) == 1
        assert body[0]["delivery_id"] == str(delivery.id)
        assert body[0]["endpoint_id"] == str(endpoint.id)
        assert body[0]["replayed"] is False

    async def test_filters_by_replayed(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        await _dead_letter(delivery_service, make_endpoint, make_event, organization_id)

        response = await client.get(
            "/webhooks/dead-letters",
            params={"organization_id": str(organization_id), "replayed": "true"},
        )

        assert response.json()["data"] == []

    async def test_is_tenant_scoped(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        await _dead_letter(delivery_service, make_endpoint, make_event, organization_id)

        response = await client.get(
            "/webhooks/dead-letters", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.json()["data"] == []

    async def test_empty_when_nothing_has_ever_dead_lettered(self, client, organization_id) -> None:
        response = await client.get(
            "/webhooks/dead-letters", params={"organization_id": str(organization_id)}
        )

        assert response.json()["data"] == []


class TestGetDeadLetterEndpoint:
    async def test_returns_the_dead_letter(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, _endpoint = await _dead_letter(
            delivery_service, make_endpoint, make_event, organization_id
        )
        listed = await delivery_service.list_dead_letters(organization_id)
        dead_letter_id = listed[0].id

        response = await client.get(
            f"/webhooks/dead-letters/{dead_letter_id}",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == HTTP_OK
        data = response.json()["data"]
        assert data["id"] == str(dead_letter_id)
        assert data["delivery_id"] == str(delivery.id)

    async def test_404_for_an_unknown_dead_letter_id(self, client, organization_id) -> None:
        response = await client.get(
            f"/webhooks/dead-letters/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == HTTP_NOT_FOUND

    async def test_404_when_the_dead_letter_belongs_to_a_different_org(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        await _dead_letter(delivery_service, make_endpoint, make_event, organization_id)
        listed = await delivery_service.list_dead_letters(organization_id)
        dead_letter_id = listed[0].id

        response = await client.get(
            f"/webhooks/dead-letters/{dead_letter_id}",
            params={"organization_id": str(uuid.uuid4())},
        )

        assert response.status_code == HTTP_NOT_FOUND
