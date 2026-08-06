"""TransformationService and WebhookTransformationRepository: rule registration and application.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

``apply_all`` is the integration point between this service and the pure
``app.transformations.engine`` module (its own dedicated, exhaustively-tested
pure module): these tests prove the service correctly routes each rule kind
to the right engine call, in priority order -- not the transformation
algorithms' own behaviour in depth.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import TransformationKind
from app.models.transformation import WebhookTransformation
from app.repositories.transformation import WebhookTransformationRepository
from app.services.transformation import TransformationService


class TestCreate:
    async def test_creates_with_defaults(
        self, transformation_service: TransformationService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        created = await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="rename-fields",
            kind=TransformationKind.FIELD_RENAME,
        )
        assert created.endpoint_id == endpoint.id
        assert created.name == "rename-fields"
        assert created.kind == TransformationKind.FIELD_RENAME
        assert created.config == {}
        assert created.priority == 100
        assert created.enabled is True
        assert created.organization_id == organization_id

    async def test_creates_with_custom_fields(
        self, transformation_service: TransformationService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        created = await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="add-header",
            kind=TransformationKind.HEADER_MAPPING,
            config={"add": {"X-Custom": "1"}},
            priority=10,
        )
        assert created.config == {"add": {"X-Custom": "1"}}
        assert created.priority == 10


class TestGet:
    async def test_returns_the_matching_transformation(
        self, transformation_service: TransformationService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        created = await transformation_service.create(
            organization_id, endpoint_id=endpoint.id, name="t", kind=TransformationKind.FIELD_REMOVAL
        )
        found = await transformation_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_a_missing_id(
        self, transformation_service: TransformationService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await transformation_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, transformation_service: TransformationService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        created = await transformation_service.create(
            organization_id, endpoint_id=endpoint.id, name="t", kind=TransformationKind.FIELD_REMOVAL
        )
        with pytest.raises(NotFoundError):
            await transformation_service.get(uuid.uuid4(), created.id)


class TestListForEndpoint:
    async def test_orders_by_priority(
        self, transformation_service: TransformationService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        low = await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="low",
            kind=TransformationKind.FIELD_REMOVAL,
            priority=50,
        )
        high = await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="high",
            kind=TransformationKind.FIELD_REMOVAL,
            priority=5,
        )
        found = await transformation_service.list_for_endpoint(endpoint.id)
        ids_in_order = [one.id for one in found]
        assert ids_in_order.index(high.id) < ids_in_order.index(low.id)

    async def test_excludes_disabled_rules(
        self,
        transformation_service: TransformationService,
        transformations_repo: WebhookTransformationRepository,
        organization_id: uuid.UUID,
        make_endpoint,
    ) -> None:
        endpoint = await make_endpoint()
        await transformations_repo.create(
            WebhookTransformation(
                organization_id=organization_id,
                endpoint_id=endpoint.id,
                name="disabled",
                kind=TransformationKind.FIELD_REMOVAL,
                enabled=False,
            )
        )
        found = await transformation_service.list_for_endpoint(endpoint.id)
        assert found == []

    async def test_scoped_by_endpoint(
        self, transformation_service: TransformationService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint_a = await make_endpoint(name="endpoint-a")
        endpoint_b = await make_endpoint(name="endpoint-b")
        created_a = await transformation_service.create(
            organization_id, endpoint_id=endpoint_a.id, name="t-a", kind=TransformationKind.FIELD_REMOVAL
        )
        await transformation_service.create(
            organization_id, endpoint_id=endpoint_b.id, name="t-b", kind=TransformationKind.FIELD_REMOVAL
        )
        found = await transformation_service.list_for_endpoint(endpoint_a.id)
        assert [one.id for one in found] == [created_a.id]


class TestApplyAll:
    async def test_no_rules_returns_payload_and_headers_unchanged(self) -> None:
        payload, headers = TransformationService.apply_all([], payload={"a": 1}, headers={"X": "1"})
        assert payload == {"a": 1}
        assert headers == {"X": "1"}

    async def test_header_mapping_rule_modifies_headers_not_payload(
        self, transformation_service: TransformationService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        rule = await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="add-header",
            kind=TransformationKind.HEADER_MAPPING,
            config={"add": {"X-Added": "yes"}, "remove": ["X-Remove-Me"]},
        )
        payload, headers = TransformationService.apply_all(
            [rule], payload={"a": 1}, headers={"X-Remove-Me": "gone"}
        )
        assert payload == {"a": 1}
        assert headers == {"X-Added": "yes"}

    async def test_non_header_rule_modifies_payload(
        self, transformation_service: TransformationService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        rule = await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="remove-secret",
            kind=TransformationKind.FIELD_REMOVAL,
            config={"fields": ["secret"]},
        )
        payload, headers = TransformationService.apply_all(
            [rule], payload={"secret": "shh", "keep": True}, headers={}
        )
        assert payload == {"keep": True}
        assert headers == {}

    async def test_multiple_rules_apply_in_the_given_order(
        self, transformation_service: TransformationService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        enrich = await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="enrich",
            kind=TransformationKind.FIELD_ENRICHMENT,
            config={"fields": {"added": "value"}},
            priority=1,
        )
        remove = await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="remove",
            kind=TransformationKind.FIELD_REMOVAL,
            config={"fields": ["added"]},
            priority=2,
        )
        payload, _headers = TransformationService.apply_all([enrich, remove], payload={}, headers={})
        assert payload == {}


class TestWebhookTransformationRepository:
    """Direct repository-level coverage for paths no service method reaches."""

    async def test_require_in_org_raises_not_found_for_other_org(
        self,
        transformations_repo: WebhookTransformationRepository,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_endpoint,
    ) -> None:
        endpoint = await make_endpoint()
        created = await transformation_service.create(
            organization_id, endpoint_id=endpoint.id, name="t", kind=TransformationKind.FIELD_REMOVAL
        )
        with pytest.raises(NotFoundError):
            await transformations_repo.require_in_org(uuid.uuid4(), created.id)
