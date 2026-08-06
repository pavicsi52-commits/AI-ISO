"""``app/api/deliveries.py`` -- the delivery-tracking REST surface.

Against the real FastAPI app (``tests/conftest.py``'s own ``client``
fixture, started through its actual lifespan) with only the request's own
database session and outbound HTTP client substituted -- see
``tests/conftest.py``'s module docstring. Test data is set up directly
through ``delivery_service`` (bound to the very same, request-shared
``db_session``) rather than through some other, untested API surface.

Neither ``GET /webhooks/deliveries`` nor ``GET /webhooks/deliveries/{id}``
take a ``CurrentUserId`` dependency, consistent with every other
read-style route in this API. ``POST /webhooks/deliveries/{id}/retry``
*does* -- it mutates and records an audit entry, like every other
mutating route -- so its own tests pass ``auth_headers``.
"""

from __future__ import annotations

import uuid

from tests.conftest import FAKE_BACKEND_URL, HTTP_BAD_REQUEST, HTTP_NOT_FOUND, HTTP_OK


async def _queue_direct(
    delivery_service, make_endpoint, make_event, organization_id, **endpoint_overrides
):
    endpoint = await make_endpoint(**endpoint_overrides)
    event = await make_event()
    delivery = await delivery_service.queue_direct(organization_id, event, endpoint_id=endpoint.id)
    return delivery, endpoint


class TestListDeliveriesEndpoint:
    async def test_lists_every_delivery_in_the_organization(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        await _queue_direct(delivery_service, make_endpoint, make_event, organization_id)
        await _queue_direct(delivery_service, make_endpoint, make_event, organization_id)

        response = await client.get(
            "/webhooks/deliveries", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        body = response.json()
        assert body["success"] is True
        assert body["message"] == "Deliveries listed."
        assert len(body["data"]) == 2

    async def test_filters_by_status(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivered, _endpoint = await _queue_direct(
            delivery_service, make_endpoint, make_event, organization_id
        )
        await delivery_service.deliver(organization_id, delivered)
        await _queue_direct(delivery_service, make_endpoint, make_event, organization_id)

        response = await client.get(
            "/webhooks/deliveries",
            params={"organization_id": str(organization_id), "status": "delivered"},
        )

        body = response.json()["data"]
        assert len(body) == 1
        assert body[0]["id"] == str(delivered.id)
        assert body[0]["status"] == "delivered"

    async def test_filters_by_endpoint_id(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery_a, endpoint_a = await _queue_direct(
            delivery_service, make_endpoint, make_event, organization_id
        )
        await _queue_direct(delivery_service, make_endpoint, make_event, organization_id)

        response = await client.get(
            "/webhooks/deliveries",
            params={"organization_id": str(organization_id), "endpoint_id": str(endpoint_a.id)},
        )

        body = response.json()["data"]
        assert [row["id"] for row in body] == [str(delivery_a.id)]

    async def test_respects_the_limit_query_param(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        for _ in range(3):
            await _queue_direct(delivery_service, make_endpoint, make_event, organization_id)

        response = await client.get(
            "/webhooks/deliveries", params={"organization_id": str(organization_id), "limit": 2}
        )

        assert len(response.json()["data"]) == 2

    async def test_is_tenant_scoped(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        await _queue_direct(delivery_service, make_endpoint, make_event, organization_id)

        response = await client.get(
            "/webhooks/deliveries", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.json()["data"] == []

    async def test_a_missing_organization_id_is_rejected(self, client) -> None:
        response = await client.get("/webhooks/deliveries")

        # `RequestValidationMiddleware` remaps FastAPI's own default 422
        # request-validation response onto this platform's own
        # `ValidationError` shape (`shared_core.exceptions.validation
        # .ValidationError.status_code == 400`) -- not the FastAPI default.
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_an_invalid_status_value_is_rejected(self, client, organization_id) -> None:
        response = await client.get(
            "/webhooks/deliveries",
            params={"organization_id": str(organization_id), "status": "not-a-real-status"},
        )

        assert response.status_code == HTTP_BAD_REQUEST


class TestGetDeliveryEndpoint:
    async def test_returns_the_delivery(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, endpoint = await _queue_direct(
            delivery_service, make_endpoint, make_event, organization_id
        )

        response = await client.get(
            f"/webhooks/deliveries/{delivery.id}", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        data = response.json()["data"]
        assert data["id"] == str(delivery.id)
        assert data["endpoint_id"] == str(endpoint.id)
        assert data["status"] == "queued"

    async def test_404_for_an_unknown_delivery_id(self, client, organization_id) -> None:
        response = await client.get(
            f"/webhooks/deliveries/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_NOT_FOUND

    async def test_404_when_the_delivery_belongs_to_a_different_org(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, _endpoint = await _queue_direct(
            delivery_service, make_endpoint, make_event, organization_id
        )

        response = await client.get(
            f"/webhooks/deliveries/{delivery.id}", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.status_code == HTTP_NOT_FOUND


class TestRetryDeliveryEndpoint:
    async def test_retrying_a_failing_delivery_returns_the_retried_status(
        self, client, delivery_service, make_endpoint, make_event, organization_id, auth_headers
    ) -> None:
        delivery, _endpoint = await _queue_direct(
            delivery_service,
            make_endpoint,
            make_event,
            organization_id,
            url=f"{FAKE_BACKEND_URL}/error",
            max_attempts=5,
        )

        response = await client.post(
            f"/webhooks/deliveries/{delivery.id}/retry",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.status_code == HTTP_OK
        data = response.json()["data"]
        assert data["status"] == "retried"
        assert data["attempt_count"] == 1
        assert data["last_error"] == "HTTP 500"

    async def test_repeated_retries_increment_the_attempt_count(
        self, client, delivery_service, make_endpoint, make_event, organization_id, auth_headers
    ) -> None:
        delivery, _endpoint = await _queue_direct(
            delivery_service,
            make_endpoint,
            make_event,
            organization_id,
            url=f"{FAKE_BACKEND_URL}/error",
            max_attempts=5,
        )
        params = {"organization_id": str(organization_id)}
        headers = auth_headers(uuid.uuid4())

        first = await client.post(
            f"/webhooks/deliveries/{delivery.id}/retry", params=params, headers=headers
        )
        second = await client.post(
            f"/webhooks/deliveries/{delivery.id}/retry", params=params, headers=headers
        )

        assert first.json()["data"]["attempt_count"] == 1
        assert second.json()["data"]["attempt_count"] == 2

    async def test_retrying_a_healthy_delivery_marks_it_delivered(
        self, client, delivery_service, make_endpoint, make_event, organization_id, auth_headers
    ) -> None:
        delivery, _endpoint = await _queue_direct(
            delivery_service, make_endpoint, make_event, organization_id
        )

        response = await client.post(
            f"/webhooks/deliveries/{delivery.id}/retry",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.json()["data"]["status"] == "delivered"

    async def test_retrying_dead_letters_once_max_attempts_is_exhausted(
        self, client, delivery_service, make_endpoint, make_event, organization_id, auth_headers
    ) -> None:
        delivery, _endpoint = await _queue_direct(
            delivery_service,
            make_endpoint,
            make_event,
            organization_id,
            url=f"{FAKE_BACKEND_URL}/error",
            max_attempts=1,
        )

        response = await client.post(
            f"/webhooks/deliveries/{delivery.id}/retry",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.json()["data"]["status"] == "expired"

    async def test_404_for_an_unknown_delivery_id(
        self, client, organization_id, auth_headers
    ) -> None:
        response = await client.post(
            f"/webhooks/deliveries/{uuid.uuid4()}/retry",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.status_code == HTTP_NOT_FOUND

    async def test_401_without_authentication(
        self, client, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, _endpoint = await _queue_direct(
            delivery_service, make_endpoint, make_event, organization_id
        )

        response = await client.post(
            f"/webhooks/deliveries/{delivery.id}/retry",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == 401

    async def test_400_when_the_endpoint_became_ssrf_unsafe_since_registration(
        self,
        client,
        delivery_service,
        endpoints_repo,
        make_endpoint,
        make_event,
        organization_id,
        auth_headers,
    ) -> None:
        delivery, endpoint = await _queue_direct(
            delivery_service, make_endpoint, make_event, organization_id
        )
        stored = await endpoints_repo.require_in_org(organization_id, endpoint.id)
        stored.url = "http://169.254.169.254/latest/meta-data"
        await endpoints_repo.update(stored)

        response = await client.post(
            f"/webhooks/deliveries/{delivery.id}/retry",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.status_code == HTTP_BAD_REQUEST
