"""TransformationService and ApiTransformationRuleRepository: rule configuration and application.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
``apply_request``/``apply_response`` are pure/static, so most of their own
tests build plain :class:`ApiTransformationRule` instances directly (never
flushed) -- the point under test is the pure function's own branching, not
persistence.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import TransformationDirection, TransformationKind
from app.models.transformation import ApiTransformationRule
from app.repositories.transformation import ApiTransformationRuleRepository
from app.services.transformation import TransformationService

# No blanket `pytestmark = pytest.mark.asyncio` here -- this module mixes
# async, DB-backed tests with plain sync tests of the pure
# `apply_request`/`apply_response` static methods, and `asyncio_mode =
# "auto"` (see pyproject.toml) already marks every `async def` test
# automatically; explicitly marking a sync test raises under this
# project's `filterwarnings = ["error", ...]`.


def _rule(
    *,
    kind: TransformationKind,
    direction: TransformationDirection = TransformationDirection.REQUEST,
    config: dict | None = None,
    priority: int = 100,
) -> ApiTransformationRule:
    """An unpersisted rule -- ``apply_request``/``apply_response`` only ever
    read ``.direction``/``.kind``/``.config`` off it, never flush it."""
    return ApiTransformationRule(
        organization_id=uuid.uuid4(),
        name="test-rule",
        kind=kind,
        direction=direction,
        config=config or {},
        priority=priority,
    )


class TestCreate:
    async def test_creates_a_rule_with_defaults(
        self, transformation_service: TransformationService, organization_id: uuid.UUID
    ) -> None:
        rule = await transformation_service.create(
            organization_id, name="add-header", kind=TransformationKind.HEADER
        )
        assert rule.id is not None
        assert rule.direction == TransformationDirection.REQUEST
        assert rule.config == {}
        assert rule.route_id is None
        assert rule.priority == 100
        assert rule.enabled is True

    async def test_creates_a_rule_with_explicit_config_route_and_priority(
        self,
        transformation_service: TransformationService,
        make_service,
        make_route,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service()
        route = await make_route(service.id)
        rule = await transformation_service.create(
            organization_id,
            name="rewrite",
            kind=TransformationKind.URL_REWRITE,
            direction=TransformationDirection.REQUEST,
            config={"pattern": "^/v1", "replacement": "/v2"},
            route_id=route.id,
            priority=10,
        )
        assert rule.route_id == route.id
        assert rule.priority == 10
        assert rule.config == {"pattern": "^/v1", "replacement": "/v2"}


class TestListForRoute:
    async def test_returns_global_and_route_specific_rules_ordered_by_priority(
        self,
        transformation_service: TransformationService,
        make_service,
        make_route,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service()
        route = await make_route(service.id)
        other_route = await make_route(service.id, name="other-route", path_pattern="/other")

        global_rule = await transformation_service.create(
            organization_id, name="global", kind=TransformationKind.HEADER, priority=50
        )
        route_rule = await transformation_service.create(
            organization_id,
            name="route-specific",
            kind=TransformationKind.BODY,
            route_id=route.id,
            priority=10,
        )
        await transformation_service.create(
            organization_id,
            name="other-route-only",
            kind=TransformationKind.BODY,
            route_id=other_route.id,
            priority=5,
        )

        rules = await transformation_service.list_for_route(organization_id, route.id)
        assert [r.id for r in rules] == [route_rule.id, global_rule.id]

    async def test_excludes_disabled_rules(
        self,
        transformations_repo: ApiTransformationRuleRepository,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
    ) -> None:
        enabled_rule = await transformation_service.create(
            organization_id, name="enabled", kind=TransformationKind.HEADER
        )
        disabled_rule = await transformation_service.create(
            organization_id, name="disabled", kind=TransformationKind.HEADER
        )
        disabled_rule.enabled = False
        await transformations_repo.update(disabled_rule)

        rules = await transformation_service.list_for_route(organization_id, None)
        assert [r.id for r in rules] == [enabled_rule.id]

    async def test_excludes_rules_from_other_organizations(
        self, transformation_service: TransformationService, organization_id: uuid.UUID
    ) -> None:
        await transformation_service.create(
            uuid.uuid4(), name="other-org", kind=TransformationKind.HEADER
        )
        rules = await transformation_service.list_for_route(organization_id, None)
        assert rules == []


class TestRepositoryRequireInOrg:
    async def test_returns_the_rule_when_it_belongs_to_the_org(
        self,
        transformations_repo: ApiTransformationRuleRepository,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
    ) -> None:
        created = await transformation_service.create(
            organization_id, name="mine", kind=TransformationKind.HEADER
        )
        found = await transformations_repo.require_in_org(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_an_unknown_id(
        self, transformations_repo: ApiTransformationRuleRepository, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await transformations_repo.require_in_org(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_rule_owned_by_a_different_org(
        self,
        transformations_repo: ApiTransformationRuleRepository,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
    ) -> None:
        created = await transformation_service.create(
            organization_id, name="mine", kind=TransformationKind.HEADER
        )
        with pytest.raises(NotFoundError):
            await transformations_repo.require_in_org(uuid.uuid4(), created.id)


class TestApplyRequestHeaders:
    def test_adds_and_removes_headers(self) -> None:
        rules = [
            _rule(
                kind=TransformationKind.HEADER,
                config={"add": {"X-Gateway": "1"}, "remove": ["X-Drop-Me"]},
            )
        ]
        headers, path, body = TransformationService.apply_request(
            rules, headers={"X-Drop-Me": "gone", "X-Keep": "yes"}, path="/x", body=None
        )
        assert headers == {"X-Keep": "yes", "X-Gateway": "1"}
        assert path == "/x"
        assert body is None

    def test_two_header_rules_touching_the_same_header_apply_in_list_order(self) -> None:
        rules = [
            _rule(kind=TransformationKind.HEADER, config={"add": {"X-Env": "first"}}, priority=10),
            _rule(kind=TransformationKind.HEADER, config={"add": {"X-Env": "second"}}, priority=20),
        ]
        headers, _, _ = TransformationService.apply_request(rules, headers={}, path="/x", body=None)
        assert headers["X-Env"] == "second"

        # Swapping the list order (as if a caller supplied the opposite
        # priority ordering) changes which value wins -- proof the function
        # applies strictly in the order given, not by re-sorting itself.
        swapped_headers, _, _ = TransformationService.apply_request(
            list(reversed(rules)), headers={}, path="/x", body=None
        )
        assert swapped_headers["X-Env"] == "first"


class TestApplyRequestUrlRewrite:
    def test_rewrites_the_path(self) -> None:
        rules = [
            _rule(
                kind=TransformationKind.URL_REWRITE,
                config={"pattern": "^/v1/", "replacement": "/v2/"},
            )
        ]
        _, path, _ = TransformationService.apply_request(
            rules, headers={}, path="/v1/orders", body=None
        )
        assert path == "/v2/orders"


class TestApplyRequestBody:
    def test_applies_body_transform_when_body_is_present(self) -> None:
        rules = [
            _rule(
                kind=TransformationKind.BODY,
                config={"add": {"injected": True}, "remove": ["secret"]},
            )
        ]
        _, _, body = TransformationService.apply_request(
            rules, headers={}, path="/x", body={"secret": "shh", "keep": 1}
        )
        assert body == {"keep": 1, "injected": True}

    def test_skips_body_transform_when_body_is_none(self) -> None:
        rules = [_rule(kind=TransformationKind.BODY, config={"add": {"injected": True}})]
        _, _, body = TransformationService.apply_request(rules, headers={}, path="/x", body=None)
        assert body is None


class TestApplyRequestDirectionAndKindFiltering:
    def test_response_direction_rules_are_skipped_entirely(self) -> None:
        rules = [
            _rule(
                kind=TransformationKind.HEADER,
                direction=TransformationDirection.RESPONSE,
                config={"add": {"X-Should-Not-Appear": "1"}},
            )
        ]
        headers, _, _ = TransformationService.apply_request(rules, headers={}, path="/x", body=None)
        assert headers == {}

    def test_an_unhandled_kind_is_a_no_op(self) -> None:
        rules = [_rule(kind=TransformationKind.SCHEMA_VALIDATION, config={"whatever": True})]
        headers, path, body = TransformationService.apply_request(
            rules, headers={"a": "b"}, path="/unchanged", body={"c": 1}
        )
        assert headers == {"a": "b"}
        assert path == "/unchanged"
        assert body == {"c": 1}


class TestApplyResponseHeaders:
    def test_adds_and_removes_headers(self) -> None:
        rules = [
            _rule(
                kind=TransformationKind.HEADER,
                direction=TransformationDirection.RESPONSE,
                config={"add": {"X-Response": "1"}, "remove": ["X-Internal"]},
            )
        ]
        headers, body = TransformationService.apply_response(
            rules, headers={"X-Internal": "secret"}, body=None
        )
        assert headers == {"X-Response": "1"}
        assert body is None


class TestApplyResponseBody:
    def test_response_mapping_kind_transforms_the_body_when_present(self) -> None:
        rules = [
            _rule(
                kind=TransformationKind.RESPONSE_MAPPING,
                direction=TransformationDirection.RESPONSE,
                config={"rename": {"old_name": "new_name"}},
            )
        ]
        _, body = TransformationService.apply_response(
            rules, headers={}, body={"old_name": "value"}
        )
        assert body == {"new_name": "value"}

    def test_body_kind_also_transforms_the_response_body(self) -> None:
        rules = [
            _rule(
                kind=TransformationKind.BODY,
                direction=TransformationDirection.RESPONSE,
                config={"add": {"wrapped": True}},
            )
        ]
        _, body = TransformationService.apply_response(rules, headers={}, body={"x": 1})
        assert body == {"x": 1, "wrapped": True}

    def test_skips_body_transform_when_body_is_none(self) -> None:
        rules = [
            _rule(
                kind=TransformationKind.RESPONSE_MAPPING,
                direction=TransformationDirection.RESPONSE,
                config={"add": {"wrapped": True}},
            )
        ]
        _, body = TransformationService.apply_response(rules, headers={}, body=None)
        assert body is None


class TestApplyResponseDirectionAndKindFiltering:
    def test_request_direction_rules_are_skipped_entirely(self) -> None:
        rules = [
            _rule(
                kind=TransformationKind.HEADER,
                direction=TransformationDirection.REQUEST,
                config={"add": {"X-Should-Not-Appear": "1"}},
            )
        ]
        headers, body = TransformationService.apply_response(rules, headers={}, body={"x": 1})
        assert headers == {}
        assert body == {"x": 1}

    def test_an_unhandled_kind_is_a_no_op(self) -> None:
        rules = [
            _rule(
                kind=TransformationKind.URL_REWRITE,
                direction=TransformationDirection.RESPONSE,
                config={"pattern": "a", "replacement": "b"},
            )
        ]
        headers, body = TransformationService.apply_response(
            rules, headers={"a": "b"}, body={"c": 1}
        )
        assert headers == {"a": "b"}
        assert body == {"c": 1}


class TestApplyRequestAndResponseAgainstPersistedOrdering:
    async def test_repo_priority_order_feeds_directly_into_apply_request(
        self, transformation_service: TransformationService, organization_id: uuid.UUID
    ) -> None:
        await transformation_service.create(
            organization_id,
            name="low-priority-first",
            kind=TransformationKind.HEADER,
            config={"add": {"X-Env": "low-priority"}},
            priority=10,
        )
        await transformation_service.create(
            organization_id,
            name="high-priority-second",
            kind=TransformationKind.HEADER,
            config={"add": {"X-Env": "high-priority"}},
            priority=90,
        )
        rules = await transformation_service.list_for_route(organization_id, None)
        headers, _, _ = TransformationService.apply_request(rules, headers={}, path="/x", body=None)
        # Repo orders ascending by priority, so the highest-priority-number
        # rule is applied last and wins the header conflict.
        assert headers["X-Env"] == "high-priority"
