"""TransformationService: connector transformation-rule registration and application.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

``apply_all`` is the integration point between this service and the pure
``app.transformations.engine`` module (its own dedicated, exhaustively-tested
pure module) -- these tests prove the service correctly loads a connector's
own *enabled* rules in *priority* order and chains one rule's output into
the next rule's input, not the transformation algorithms' own behaviour in
depth.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import DataFormat, TransformationKind
from app.models.transformation import ConnectorTransformation
from app.repositories.transformation import ConnectorTransformationRepository
from app.services.transformation import TransformationService

pytestmark = pytest.mark.asyncio


class TestCreate:
    async def test_creates_with_defaults(
        self,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()

        created = await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="map-fields",
            kind=TransformationKind.FIELD_MAPPING,
        )

        assert created.connector_id == connector.id
        assert created.name == "map-fields"
        assert created.kind == TransformationKind.FIELD_MAPPING
        assert created.source_format == DataFormat.JSON
        assert created.target_format == DataFormat.JSON
        assert created.config == {}
        assert created.priority == 100
        assert created.enabled is True
        assert created.organization_id == organization_id

    async def test_creates_with_custom_fields(
        self,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()

        created = await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="csv-to-json",
            kind=TransformationKind.FORMAT_CONVERSION,
            source_format=DataFormat.CSV,
            target_format=DataFormat.JSON,
            config={"source_format": "csv", "target_format": "json"},
            priority=5,
        )

        assert created.source_format == DataFormat.CSV
        assert created.target_format == DataFormat.JSON
        assert created.config == {"source_format": "csv", "target_format": "json"}
        assert created.priority == 5


class TestGet:
    async def test_returns_the_matching_transformation(
        self,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        created = await transformation_service.create(
            organization_id, connector_id=connector.id, name="t", kind=TransformationKind.ENRICHMENT
        )

        found = await transformation_service.get(organization_id, created.id)

        assert found.id == created.id

    async def test_raises_not_found_for_a_missing_id(
        self, transformation_service: TransformationService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await transformation_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        created = await transformation_service.create(
            organization_id, connector_id=connector.id, name="t", kind=TransformationKind.ENRICHMENT
        )

        with pytest.raises(NotFoundError):
            await transformation_service.get(uuid.uuid4(), created.id)


class TestListForConnector:
    async def test_orders_by_priority(
        self,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        low = await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="low",
            kind=TransformationKind.ENRICHMENT,
            priority=50,
        )
        high = await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="high",
            kind=TransformationKind.ENRICHMENT,
            priority=5,
        )

        found = await transformation_service.list_for_connector(connector.id)

        ids_in_order = [row.id for row in found]
        assert ids_in_order.index(high.id) < ids_in_order.index(low.id)

    async def test_enabled_true_excludes_disabled_rules(
        self,
        transformation_service: TransformationService,
        transformations_repo: ConnectorTransformationRepository,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        enabled = await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="enabled",
            kind=TransformationKind.ENRICHMENT,
        )
        await transformations_repo.create(
            ConnectorTransformation(
                organization_id=organization_id,
                connector_id=connector.id,
                name="disabled",
                kind=TransformationKind.ENRICHMENT,
                enabled=False,
            )
        )

        found = await transformation_service.list_for_connector(connector.id, enabled=True)

        assert [row.id for row in found] == [enabled.id]

    async def test_enabled_false_returns_only_disabled_rules(
        self,
        transformation_service: TransformationService,
        transformations_repo: ConnectorTransformationRepository,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="enabled",
            kind=TransformationKind.ENRICHMENT,
        )
        disabled = await transformations_repo.create(
            ConnectorTransformation(
                organization_id=organization_id,
                connector_id=connector.id,
                name="disabled",
                kind=TransformationKind.ENRICHMENT,
                enabled=False,
            )
        )

        found = await transformation_service.list_for_connector(connector.id, enabled=False)

        assert [row.id for row in found] == [disabled.id]

    async def test_no_filter_returns_both_enabled_and_disabled(
        self,
        transformation_service: TransformationService,
        transformations_repo: ConnectorTransformationRepository,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        enabled = await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="enabled",
            kind=TransformationKind.ENRICHMENT,
        )
        disabled = await transformations_repo.create(
            ConnectorTransformation(
                organization_id=organization_id,
                connector_id=connector.id,
                name="disabled",
                kind=TransformationKind.ENRICHMENT,
                enabled=False,
            )
        )

        found = await transformation_service.list_for_connector(connector.id)

        assert {row.id for row in found} == {enabled.id, disabled.id}

    async def test_scoped_by_connector(
        self,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector_a = await make_connector(name="connector-a")
        connector_b = await make_connector(name="connector-b")
        created_a = await transformation_service.create(
            organization_id,
            connector_id=connector_a.id,
            name="t-a",
            kind=TransformationKind.ENRICHMENT,
        )
        await transformation_service.create(
            organization_id,
            connector_id=connector_b.id,
            name="t-b",
            kind=TransformationKind.ENRICHMENT,
        )

        found = await transformation_service.list_for_connector(connector_a.id)

        assert [row.id for row in found] == [created_a.id]


class TestApplyAll:
    async def test_no_rules_returns_data_unchanged(
        self, transformation_service: TransformationService, make_connector
    ) -> None:
        connector = await make_connector()

        result = await transformation_service.apply_all(connector.id, {"a": 1})

        assert result == {"a": 1}

    async def test_field_mapping_then_enrichment_chain_and_both_apply(
        self,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        # Runs first (lower priority number).
        await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="rename-old-to-new",
            kind=TransformationKind.FIELD_MAPPING,
            config={"mapping": {"old_name": "new_name"}},
            priority=10,
        )
        # Runs second -- only adds `"tag"` since it is missing; must not
        # clobber the field the mapping rule already produced.
        await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="add-tag",
            kind=TransformationKind.ENRICHMENT,
            config={"fields": {"tag": "added"}},
            priority=20,
        )

        result = await transformation_service.apply_all(connector.id, {"old_name": "value-123"})

        assert result == {"new_name": "value-123", "tag": "added"}
        assert "old_name" not in result

    async def test_rules_apply_in_priority_order_not_creation_order(
        self,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        # Created *second* but must run *first* (lower priority number):
        # enrichment adds a lowercase default only when the field is
        # missing.
        await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="add-default-greeting",
            kind=TransformationKind.ENRICHMENT,
            config={"fields": {"greeting": "hi"}},
            priority=5,
        )
        # Created *first* but must run *second*: uppercases the field --
        # a no-op if the field does not exist yet.
        await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="uppercase-greeting",
            kind=TransformationKind.NORMALIZATION,
            config={"rules": {"greeting": "uppercase"}},
            priority=10,
        )

        result = await transformation_service.apply_all(connector.id, {})

        # If normalization had run before enrichment (creation order),
        # `greeting` would not exist yet and the uppercase rule would be a
        # no-op, leaving `"hi"` (lowercase) rather than `"HI"`.
        assert result == {"greeting": "HI"}

    async def test_a_disabled_rule_is_skipped(
        self,
        transformation_service: TransformationService,
        transformations_repo: ConnectorTransformationRepository,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        await transformations_repo.create(
            ConnectorTransformation(
                organization_id=organization_id,
                connector_id=connector.id,
                name="disabled-enrichment",
                kind=TransformationKind.ENRICHMENT,
                config={"fields": {"should_not_appear": True}},
                enabled=False,
            )
        )

        result = await transformation_service.apply_all(connector.id, {"a": 1})

        assert result == {"a": 1}

    async def test_rules_from_another_connector_are_not_applied(
        self,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector_a = await make_connector(name="connector-a")
        connector_b = await make_connector(name="connector-b")
        await transformation_service.create(
            organization_id,
            connector_id=connector_b.id,
            name="only-for-b",
            kind=TransformationKind.ENRICHMENT,
            config={"fields": {"from_b": True}},
        )

        result = await transformation_service.apply_all(connector_a.id, {"a": 1})

        assert result == {"a": 1}
