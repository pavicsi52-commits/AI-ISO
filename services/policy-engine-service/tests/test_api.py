"""The HTTP contract, through the real application.

Driven with ``httpx.ASGITransport`` against an app started through its
actual lifespan: real PostgreSQL, real Redis, real RabbitMQ, real key
loading, real middleware, real exception handlers.

Two things are asserted here that no service-level test can reach:

- **Every business route requires authentication.** For the service that
  authorizes every protected operation on the platform, an unguarded
  route is not a bug, it is a bypass.
- **`POST /policies/evaluate` answers 200 for a refusal.** A denial is a
  successful decision. Getting this wrong would force every caller to
  tell an authorization *outcome* apart from an authorization *failure*
  by parsing a body -- and the ones that got it wrong would fail open.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.models.enums import (
    ActionType,
    ApprovalStatus,
    AttributeSource,
    PolicyEffect,
    PolicyStatus,
    QuotaPeriod,
    QuotaScope,
    ReportKind,
    ResourceType,
    RuleOperator,
    SubjectType,
)
from tests.conftest import AuthHeadersFn, PublishedPolicyFn, utcnow

# No module-level asyncio mark: this file mixes synchronous schema
# assertions with async ones, and `asyncio_mode = "auto"` already
# collects the async ones. Marking a sync test asyncio is a warning,
# which this suite turns into a failure.

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409

CALLER = uuid.UUID("11111111-1111-1111-1111-111111111111")

UNAUTHENTICATED_PATHS = frozenset({"/health", "/liveness", "/readiness", "/metrics"})
"""Routes that must answer without a token.

Health probes are called by Kubernetes, which has no bearer token, and
``/metrics`` by Prometheus. Everything else must refuse.
"""


def org(organization_id: uuid.UUID) -> dict[str, str]:
    """The organization query parameter every business route takes."""
    return {"organization_id": str(organization_id)}


def operations(app: FastAPI) -> list[tuple[str, str]]:
    """Every documented ``(method, path)`` this service exposes.

    Read from the OpenAPI document rather than by walking ``app.routes``:
    this FastAPI keeps an included router nested rather than flattening
    it, and the generated document is the contract a client actually
    sees.
    """
    return sorted(
        (method.upper(), path)
        for path, methods in app.openapi()["paths"].items()
        for method in methods
        if method.lower() not in ("head", "options")
    )


def rule_payload(
    path: str = "department",
    operator: RuleOperator = RuleOperator.EQUALS,
    value: Any = "platform",
) -> dict[str, Any]:
    """A one-condition rule tree, as the API takes it."""
    return {
        "rule": {
            "name": "root",
            "logical_operator": "all",
            "conditions": [
                {
                    "source": str(AttributeSource.SUBJECT),
                    "path": path,
                    "operator": str(operator),
                    "value": value,
                }
            ],
        }
    }


def evaluate_body(**overrides: Any) -> dict[str, Any]:
    """An evaluation request with sensible defaults."""
    return {
        "subject_type": str(SubjectType.USER),
        "subject_id": "user-1",
        "resource_type": str(ResourceType.DASHBOARD),
        "action": str(ActionType.READ),
        "attributes": {"subject": {"department": "platform"}},
        **overrides,
    }


class TestAuthentication:
    """No business route answers without a token."""

    def test_the_route_table_matches_the_specification(self, app: FastAPI) -> None:
        # Asserted so a router that stopped being included fails loudly
        # rather than turning every one of its tests into a 404.
        assert len(operations(app)) == 43

    def test_every_documented_path_is_under_policies_or_a_probe(self, app: FastAPI) -> None:
        for _method, path in operations(app):
            assert path.startswith(("/policies", "/health", "/liveness", "/readiness", "/metrics"))

    def test_no_route_is_versioned_in_its_own_path(self, app: FastAPI) -> None:
        # The gateway owns versioning; a service that prefixed /api/v1
        # itself would be reachable at /api/v1/api/v1/... through it.
        for _method, path in operations(app):
            assert not path.startswith("/api/")

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/policies"),
            ("post", "/policies"),
            ("post", "/policies/evaluate"),
            ("post", "/policies/simulate"),
            ("get", "/policies/conflicts"),
            ("get", "/policies/simulations"),
            ("post", "/policies/publish"),
            ("post", "/policies/rollback"),
            ("post", "/policies/guardrails/seed"),
            ("get", "/policies/decisions"),
            ("get", "/policies/violations"),
            ("get", "/policies/exceptions"),
            ("post", "/policies/exceptions"),
            ("get", "/policies/exceptions/overused"),
            ("get", "/policies/approvals"),
            ("get", "/policies/quotas"),
            ("post", "/policies/quotas"),
            ("put", "/policies/quotas"),
            ("post", "/policies/quotas/reset"),
            ("get", "/policies/statistics"),
            ("get", "/policies/reports"),
            ("post", "/policies/reports"),
            ("get", "/policies/audit"),
            ("get", "/policies/audit/summary"),
            ("get", "/policies/attributes"),
        ],
    )
    async def test_every_business_route_refuses_an_anonymous_caller(
        self, method: str, path: str, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        # For the service that authorizes every protected operation on the
        # platform, an unguarded route is not a bug -- it is a bypass.
        response = await client.request(
            method.upper(),
            path,
            params=org(organization_id),
            **({"json": {}} if method in ("post", "put", "patch") else {}),
        )
        assert response.status_code == HTTP_UNAUTHORIZED, f"{method.upper()} {path}"

    @pytest.mark.parametrize("path", sorted(UNAUTHENTICATED_PATHS))
    async def test_the_probes_answer_without_a_token(self, path: str, client: AsyncClient) -> None:
        assert (await client.get(path)).status_code == HTTP_OK

    async def test_a_malformed_token_is_refused(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/policies",
            params=org(organization_id),
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert response.status_code == HTTP_UNAUTHORIZED


class TestHealth:
    """What the orchestrator reads."""

    async def test_liveness_says_only_that_the_process_is_up(self, client: AsyncClient) -> None:
        assert (await client.get("/liveness")).status_code == HTTP_OK

    async def test_readiness_reports_each_dependency(self, client: AsyncClient) -> None:
        payload = (await client.get("/readiness")).json()
        named = {one["name"] for one in payload["data"]["checks"]}
        assert {"database", "cache"} <= named

    async def test_readiness_gates_on_the_database(self, client: AsyncClient) -> None:
        # This service cannot decide anything without its catalogue, so a
        # replica taking traffic with no database fails closed on every
        # request -- safe, but indistinguishable from an outage.
        payload = (await client.get("/readiness")).json()
        database = next(one for one in payload["data"]["checks"] if one["name"] == "database")
        assert database["status"] == "ok"
        assert payload["data"]["status"] == "ready"

    async def test_health_reports_status_and_environment(self, client: AsyncClient) -> None:
        payload = (await client.get("/health")).json()
        assert payload["data"]["status"] == "healthy"
        assert payload["data"]["environment"]

    async def test_metrics_are_exposed_for_prometheus(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        assert response.status_code == HTTP_OK
        assert "python_info" in response.text


class TestPolicyRoutes:
    """Authoring over HTTP."""

    async def test_creating_a_policy_returns_201_in_draft(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/policies",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"slug": "p1", "name": "P1", "effect": str(PolicyEffect.DENY)},
        )
        assert response.status_code == HTTP_CREATED
        assert response.json()["data"]["status"] == str(PolicyStatus.DRAFT)

    async def test_the_create_schema_has_no_status_field(self, app: FastAPI) -> None:
        # A policy creatable already published would let the whole review
        # pipeline be bypassed by one extra field on a create call.
        schema = app.openapi()["components"]["schemas"]["PolicyCreateRequest"]
        assert "status" not in schema["properties"]

    async def test_a_malformed_slug_is_refused(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/policies",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"slug": "Not A Slug", "name": "P1", "effect": str(PolicyEffect.DENY)},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_a_duplicate_slug_is_a_409(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        body = {"slug": "p1", "name": "P1", "effect": str(PolicyEffect.DENY)}
        first = await client.post(
            "/policies", params=org(organization_id), headers=auth_headers(CALLER), json=body
        )
        assert first.status_code == HTTP_CREATED
        second = await client.post(
            "/policies", params=org(organization_id), headers=auth_headers(CALLER), json=body
        )
        assert second.status_code == HTTP_CONFLICT

    async def test_listing_and_reading_one_policy(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        published = await make_policy("p1", PolicyEffect.DENY)
        listed = await client.get(
            "/policies", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert [one["slug"] for one in listed.json()["data"]] == ["p1"]

        one = await client.get(
            f"/policies/{published.id}",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert one.json()["data"]["slug"] == "p1"

    async def test_a_missing_policy_is_a_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            f"/policies/{uuid.uuid4()}",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_a_policy_from_another_organization_is_a_404(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # 404 rather than 403: telling a caller a policy exists but
        # belongs to someone else confirms the id.
        published = await make_policy("p1", PolicyEffect.DENY)
        response = await client.get(
            f"/policies/{published.id}",
            params=org(uuid.uuid4()),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_updating_a_policy(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        published = await make_policy("p1", PolicyEffect.DENY)
        response = await client.put(
            f"/policies/{published.id}",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"priority": 750},
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["priority"] == 750
        assert "Publish to make the change live" in response.json()["message"]

    async def test_archiving_a_policy(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        published = await make_policy("p1", PolicyEffect.DENY)
        response = await client.delete(
            f"/policies/{published.id}",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["archived"] is True

    async def test_a_literal_segment_is_not_parsed_as_a_policy_id(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # Router order is load-bearing: /policies/decisions would
        # otherwise resolve as a policy whose id is the word "decisions"
        # and answer 400 for a malformed UUID.
        for path in (
            "/policies/decisions",
            "/policies/quotas",
            "/policies/audit",
            "/policies/statistics",
            "/policies/attributes",
            "/policies/violations",
            "/policies/exceptions",
            "/policies/approvals",
            "/policies/reports",
            "/policies/conflicts",
            "/policies/simulations",
        ):
            response = await client.get(
                path, params=org(organization_id), headers=auth_headers(CALLER)
            )
            assert response.status_code == HTTP_OK, f"{path} was shadowed"


class TestRulesAndPublishing:
    """Authoring rules and making them live."""

    async def _draft(
        self, client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID
    ) -> str:
        created = await client.post(
            "/policies",
            params=org(organization_id),
            headers=headers,
            json={"slug": "p1", "name": "P1", "effect": str(PolicyEffect.DENY)},
        )
        return str(created.json()["data"]["id"])

    async def _approve(
        self,
        client: AsyncClient,
        headers: dict[str, str],
        organization_id: uuid.UUID,
        policy_id: str,
    ) -> None:
        """Walk a draft to APPROVED over HTTP, which publishing requires."""
        for target in (PolicyStatus.REVIEW, PolicyStatus.APPROVED):
            response = await client.post(
                f"/policies/{policy_id}/transition",
                params=org(organization_id),
                headers=headers,
                json={"target": str(target)},
            )
            assert response.status_code == HTTP_OK, response.text

    async def test_publishing_an_unapproved_draft_is_a_409(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        """The one move the lifecycle table calls impossible.

        ``publish`` is the only operation that changes live
        authorization, so it is the only place the review states can
        actually be enforced -- and it used to be a second, unlocked door
        into exactly the state ``transition`` refuses to move a draft
        into. Found by driving the real API end to end against the built
        image; every service-level test had dutifully walked the legal
        path first and so never tried the illegal one.
        """
        headers = auth_headers(CALLER)
        policy_id = await self._draft(client, headers, organization_id)
        await client.put(
            f"/policies/{policy_id}/rules",
            params=org(organization_id),
            headers=headers,
            json=rule_payload(),
        )
        response = await client.post(
            "/policies/publish",
            params={**org(organization_id), "policy_id": policy_id},
            headers=headers,
            json={},
        )
        # The platform handler returns a deliberately generic message on
        # 4xx; the reason is asserted at service level, where it is
        # visible. What matters here is that the door is shut.
        assert response.status_code == HTTP_CONFLICT

    async def test_setting_a_rule_tree_counts_the_conditions(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        policy_id = await self._draft(client, headers, organization_id)
        response = await client.put(
            f"/policies/{policy_id}/rules",
            params=org(organization_id),
            headers=headers,
            json=rule_payload(),
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["conditions"] == 1

    async def test_an_empty_rule_is_refused(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # An empty ALL rule is vacuously true, so a policy carrying one
        # would match every request in the estate.
        headers = auth_headers(CALLER)
        policy_id = await self._draft(client, headers, organization_id)
        response = await client.put(
            f"/policies/{policy_id}/rules",
            params=org(organization_id),
            headers=headers,
            json={"rule": {"name": "empty", "logical_operator": "all", "conditions": []}},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_an_unusable_pattern_is_refused_at_authoring_time(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        policy_id = await self._draft(client, headers, organization_id)
        response = await client.put(
            f"/policies/{policy_id}/rules",
            params=org(organization_id),
            headers=headers,
            json=rule_payload("name", RuleOperator.MATCHES, "(unclosed"),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_a_draft_cannot_transition_straight_to_published(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        policy_id = await self._draft(client, headers, organization_id)
        response = await client.post(
            f"/policies/{policy_id}/transition",
            params=org(organization_id),
            headers=headers,
            json={"target": str(PolicyStatus.PUBLISHED)},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_publishing_makes_a_policy_live(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        policy_id = await self._draft(client, headers, organization_id)
        await client.put(
            f"/policies/{policy_id}/rules",
            params=org(organization_id),
            headers=headers,
            json=rule_payload(),
        )
        await self._approve(client, headers, organization_id, policy_id)
        response = await client.post(
            "/policies/publish",
            params={**org(organization_id), "policy_id": policy_id},
            headers=headers,
            json={"change_summary": "first version"},
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["status"] == str(PolicyStatus.PUBLISHED)
        assert response.json()["data"]["semantic_version"] == "1.0.1"

    async def test_publishing_without_rules_is_a_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        policy_id = await self._draft(client, headers, organization_id)
        await self._approve(client, headers, organization_id, policy_id)
        response = await client.post(
            "/policies/publish",
            params={**org(organization_id), "policy_id": policy_id},
            headers=headers,
            json={},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_versions_and_verification(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        published = await make_policy("p1", PolicyEffect.DENY)
        versions = await client.get(
            f"/policies/{published.id}/versions",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert len(versions.json()["data"]) == 1

        verified = await client.get(
            f"/policies/{published.id}/verify",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert verified.json()["data"]["verified"] is True

    async def test_rollback_with_a_single_version_is_a_400(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        published = await make_policy("p1", PolicyEffect.DENY)
        response = await client.post(
            "/policies/rollback",
            params={**org(organization_id), "policy_id": str(published.id)},
            headers=auth_headers(CALLER),
            json={},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_seeding_guardrails_is_idempotent_over_http(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        first = await client.post(
            "/policies/guardrails/seed", params=org(organization_id), headers=headers
        )
        assert first.status_code == HTTP_OK
        assert len(first.json()["data"]) > 0

        second = await client.post(
            "/policies/guardrails/seed", params=org(organization_id), headers=headers
        )
        assert second.json()["data"] == []


class TestEvaluation:
    """The endpoint every other service calls."""

    async def test_an_empty_catalogue_denies_with_200(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # A denial is a *successful* decision. Answering 403 would
        # conflate "you may not do that" with "you may not ask", and
        # force every caller to tell an authorization outcome apart from
        # an authorization failure by parsing a body.
        response = await client.post(
            "/policies/evaluate",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json=evaluate_body(),
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["permitted"] is False
        assert response.json()["data"]["effect"] == str(PolicyEffect.DENY)

    async def test_a_matching_allow_permits(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        response = await client.post(
            "/policies/evaluate",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json=evaluate_body(),
        )
        assert response.json()["data"]["permitted"] is True

    async def test_the_response_carries_its_reasoning(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # "The policy engine said no" is not an answer anybody can act on.
        await make_policy("deny-platform", PolicyEffect.DENY)
        payload = (
            await client.post(
                "/policies/evaluate",
                params=org(organization_id),
                headers=auth_headers(CALLER),
                json=evaluate_body(),
            )
        ).json()["data"]
        assert payload["reason"]
        assert payload["deciding_policy_id"]
        assert payload["trace"]
        assert payload["decision_id"]

    async def test_an_approval_requirement_is_not_a_permit(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # The distinction that keeps approval gates real: a client
        # checking one boolean must not have obligations filed under
        # permitted.
        await make_policy(
            "review-platform",
            PolicyEffect.REQUIRE_APPROVAL,
            obligations={"approval_type": "single", "levels": 1},
        )
        payload = (
            await client.post(
                "/policies/evaluate",
                params=org(organization_id),
                headers=auth_headers(CALLER),
                json=evaluate_body(),
            )
        ).json()["data"]
        assert payload["effect"] == str(PolicyEffect.REQUIRE_APPROVAL)
        assert payload["permitted"] is False
        assert payload["denied"] is False

    async def test_an_approval_requirement_raises_an_actionable_obligation(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # So the caller gets an approval id it can point somebody at
        # rather than a refusal with no route forward.
        await make_policy(
            "review-platform",
            PolicyEffect.REQUIRE_APPROVAL,
            obligations={"approval_type": "single", "levels": 1},
        )
        payload = (
            await client.post(
                "/policies/evaluate",
                params=org(organization_id),
                headers=auth_headers(CALLER),
                json=evaluate_body(),
            )
        ).json()["data"]
        assert payload["obligations"]["approval_id"]
        assert payload["obligations"]["approval_expires_at"]

        approvals = await client.get(
            "/policies/approvals", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert len(approvals.json()["data"]) == 1

    async def test_a_dry_run_records_nothing(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await client.post(
            "/policies/evaluate",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json=evaluate_body(record=False),
        )
        decisions = await client.get(
            "/policies/decisions", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert decisions.json()["data"] == []

    async def test_a_decision_is_findable_by_request_id(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("deny-platform", PolicyEffect.DENY)
        await client.post(
            "/policies/evaluate",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json=evaluate_body(request_id="trace-me"),
        )
        found = await client.get(
            "/policies/decisions/by-request/trace-me",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert found.status_code == HTTP_OK
        assert found.json()["data"]["request_id"] == "trace-me"

    async def test_an_unknown_request_id_is_a_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/policies/decisions/by-request/nope",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_a_refusal_is_audited_as_denied(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("deny-platform", PolicyEffect.DENY)
        await client.post(
            "/policies/evaluate",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json=evaluate_body(),
        )
        audit = await client.get(
            "/policies/audit", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert any(one["outcome"] == "denied" for one in audit.json()["data"])

    async def test_the_decision_response_is_serialisable(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("deny-platform", PolicyEffect.DENY)
        payload = (
            await client.post(
                "/policies/evaluate",
                params=org(organization_id),
                headers=auth_headers(CALLER),
                json=evaluate_body(),
            )
        ).json()
        assert json.dumps(payload)


class TestSimulationRoutes:
    """Rehearsals over HTTP."""

    def _request(self) -> dict[str, Any]:
        return {
            "label": "read-dashboard",
            "subject_type": str(SubjectType.USER),
            "resource_type": str(ResourceType.DASHBOARD),
            "action": str(ActionType.READ),
            "subject": {"department": "platform"},
        }

    async def test_a_stored_simulation_reports_what_changed(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        draft = await make_policy("deny-draft", PolicyEffect.DENY, publish=False)

        response = await client.post(
            "/policies/simulate",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "label": "what-if",
                "requests": [self._request()],
                "draft_policy_ids": [str(draft.id)],
            },
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["changed_count"] == 1

    async def test_a_preview_is_not_stored(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await client.post(
            "/policies/simulate",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"requests": [self._request()], "store": False},
        )
        listed = await client.get(
            "/policies/simulations", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert listed.json()["data"] == []

    async def test_a_preview_reports_whether_a_change_is_safe(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        denier = await make_policy("deny-all", PolicyEffect.DENY)
        response = await client.post(
            "/policies/simulate",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "requests": [self._request()],
                "excluded_policy_ids": [str(denier.id)],
                "store": False,
            },
        )
        assert response.json()["data"]["safe"] is True

    async def test_an_empty_simulation_is_a_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/policies/simulate",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"requests": []},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_conflicts_are_reported_as_potential(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await make_policy("deny-platform", PolicyEffect.DENY)
        response = await client.get(
            "/policies/conflicts", params=org(organization_id), headers=auth_headers(CALLER)
        )
        conflicts = response.json()["data"]
        assert len(conflicts) == 1
        assert "Potential conflict" in conflicts[0]["note"]


class TestApprovalRoutes:
    """Obligations over HTTP."""

    async def _raise(
        self,
        client: AsyncClient,
        headers: dict[str, str],
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
        *,
        levels: int = 1,
    ) -> str:
        await make_policy(
            "review-platform",
            PolicyEffect.REQUIRE_APPROVAL,
            obligations={
                "approval_type": "multi_level" if levels > 1 else "single",
                "levels": levels,
            },
        )
        payload = (
            await client.post(
                "/policies/evaluate",
                params=org(organization_id),
                headers=headers,
                json=evaluate_body(),
            )
        ).json()["data"]
        return str(payload["obligations"]["approval_id"])

    async def test_an_approval_can_be_granted(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        headers = auth_headers(CALLER)
        approval_id = await self._raise(client, headers, make_policy, organization_id)
        response = await client.post(
            f"/policies/approvals/{approval_id}/decide",
            params=org(organization_id),
            headers=headers,
            json={"approver_id": "alice", "approved": True},
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["status"] == str(ApprovalStatus.APPROVED)

    async def test_one_rejection_ends_a_multi_level_approval(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        headers = auth_headers(CALLER)
        approval_id = await self._raise(client, headers, make_policy, organization_id, levels=3)
        await client.post(
            f"/policies/approvals/{approval_id}/decide",
            params=org(organization_id),
            headers=headers,
            json={"approver_id": "alice", "approved": True},
        )
        response = await client.post(
            f"/policies/approvals/{approval_id}/decide",
            params=org(organization_id),
            headers=headers,
            json={"approver_id": "bob", "approved": False},
        )
        assert response.json()["data"]["status"] == str(ApprovalStatus.REJECTED)

    async def test_the_same_approver_cannot_answer_twice(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        headers = auth_headers(CALLER)
        approval_id = await self._raise(client, headers, make_policy, organization_id, levels=2)
        await client.post(
            f"/policies/approvals/{approval_id}/decide",
            params=org(organization_id),
            headers=headers,
            json={"approver_id": "alice", "approved": True},
        )
        response = await client.post(
            f"/policies/approvals/{approval_id}/decide",
            params=org(organization_id),
            headers=headers,
            json={"approver_id": "alice", "approved": True},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_reading_one_approval_reports_its_derived_state(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        headers = auth_headers(CALLER)
        approval_id = await self._raise(client, headers, make_policy, organization_id)
        response = await client.get(
            f"/policies/approvals/{approval_id}",
            params=org(organization_id),
            headers=headers,
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["state"]["status"] == str(ApprovalStatus.PENDING)


class TestQuotaRoutes:
    """Budgets over HTTP."""

    async def test_defining_and_listing_a_quota(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        created = await client.post(
            "/policies/quotas",
            params=org(organization_id),
            headers=headers,
            json={
                "scope": str(QuotaScope.ORGANIZATION),
                "scope_id": str(organization_id),
                "resource": "api_calls",
                "limit_value": 100,
                "period": str(QuotaPeriod.DAILY),
            },
        )
        assert created.status_code == HTTP_CREATED

        listed = await client.get("/policies/quotas", params=org(organization_id), headers=headers)
        assert [one["resource"] for one in listed.json()["data"]] == ["api_calls"]

    async def test_a_zero_limit_is_reported_as_unlimited(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # A quota created without a limit would otherwise refuse every
        # request for that resource, and an accidental total outage is
        # far worse than an accidental absence of enforcement.
        response = await client.post(
            "/policies/quotas",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "scope": str(QuotaScope.ORGANIZATION),
                "scope_id": str(organization_id),
                "resource": "api_calls",
                "limit_value": 0,
            },
        )
        assert "unlimited" in response.json()["message"]

    async def test_a_duplicate_quota_is_a_409(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        body = {
            "scope": str(QuotaScope.ORGANIZATION),
            "scope_id": str(organization_id),
            "resource": "api_calls",
            "limit_value": 10,
        }
        await client.post(
            "/policies/quotas", params=org(organization_id), headers=headers, json=body
        )
        second = await client.post(
            "/policies/quotas", params=org(organization_id), headers=headers, json=body
        )
        assert second.status_code == HTTP_CONFLICT

    async def test_an_exhausted_quota_refuses_the_next_request(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        headers = auth_headers(CALLER)
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await client.post(
            "/policies/quotas",
            params=org(organization_id),
            headers=headers,
            json={
                "scope": str(QuotaScope.ORGANIZATION),
                "scope_id": str(organization_id),
                "resource": "requests",
                "limit_value": 1,
            },
        )
        first = await client.post(
            "/policies/evaluate",
            params=org(organization_id),
            headers=headers,
            json=evaluate_body(),
        )
        assert first.json()["data"]["permitted"] is True

        second = await client.post(
            "/policies/evaluate",
            params=org(organization_id),
            headers=headers,
            json=evaluate_body(),
        )
        # A distinguishable refusal: "out of budget" needs a different
        # response from "not permitted".
        assert second.json()["data"]["effect"] == str(PolicyEffect.QUOTA_EXCEEDED)

    async def test_updating_and_resetting_a_quota(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        params = {
            **org(organization_id),
            "scope": str(QuotaScope.ORGANIZATION),
            "scope_id": str(organization_id),
            "resource": "requests",
        }
        await client.post(
            "/policies/quotas",
            params=org(organization_id),
            headers=headers,
            json={
                "scope": str(QuotaScope.ORGANIZATION),
                "scope_id": str(organization_id),
                "resource": "requests",
                "limit_value": 10,
            },
        )
        updated = await client.put(
            "/policies/quotas", params=params, headers=headers, json={"limit_value": 500}
        )
        assert updated.json()["data"]["limit_value"] == 500

        reset = await client.post("/policies/quotas/reset", params=params, headers=headers)
        assert reset.json()["data"]["consumed"] == 0

    async def test_updating_a_missing_quota_is_a_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.put(
            "/policies/quotas",
            params={**org(organization_id), "scope_id": "nope", "resource": "requests"},
            headers=auth_headers(CALLER),
            json={"limit_value": 5},
        )
        assert response.status_code == HTTP_NOT_FOUND


class TestComplianceRoutes:
    """Violations and exceptions over HTTP."""

    async def test_an_exception_needs_an_expiry(self, app: FastAPI) -> None:
        # Required by the schema, not merely by the service: a permanent
        # exception is not an exception.
        schema = app.openapi()["components"]["schemas"]["ExceptionCreateRequest"]
        assert "expires_at" in schema["required"]
        assert "reason" in schema["required"]

    async def test_granting_and_revoking_an_exception(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        headers = auth_headers(CALLER)
        target = await make_policy("deny-platform", PolicyEffect.DENY)

        granted = await client.post(
            "/policies/exceptions",
            params=org(organization_id),
            headers=headers,
            json={
                "policy_id": str(target.id),
                "reason": "migration window",
                "expires_at": (utcnow() + timedelta(days=1)).isoformat(),
            },
        )
        assert granted.status_code == HTTP_CREATED
        exception_id = granted.json()["data"]["id"]

        revoked = await client.delete(
            f"/policies/exceptions/{exception_id}",
            params=org(organization_id),
            headers=headers,
        )
        assert revoked.status_code == HTTP_OK
        assert revoked.json()["data"]["revoked_at"]

    async def test_an_over_long_exception_is_a_400(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        target = await make_policy("deny-platform", PolicyEffect.DENY)
        response = await client.post(
            "/policies/exceptions",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "policy_id": str(target.id),
                "reason": "forever",
                "expires_at": (utcnow() + timedelta(days=400)).isoformat(),
            },
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_overused_exceptions_can_be_listed(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/policies/exceptions/overused",
            params={**org(organization_id), "threshold": 10},
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK

    async def test_violations_can_be_listed(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/policies/violations", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"] == []

    async def test_resolving_a_violation_needs_a_note(self, app: FastAPI) -> None:
        schema = app.openapi()["components"]["schemas"]["ViolationResolveRequest"]
        assert "note" in schema["required"]


class TestOperationsRoutes:
    """Statistics, reports, audit, and the attribute catalogue."""

    async def test_statistics_are_computed_on_demand(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("p1", PolicyEffect.DENY)
        response = await client.get(
            "/policies/statistics",
            params={**org(organization_id), "recompute": True},
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["published_count"] == 1

    @pytest.mark.parametrize("kind", list(ReportKind))
    async def test_every_report_kind_generates_over_http(
        self,
        kind: ReportKind,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("p1", PolicyEffect.DENY)
        response = await client.post(
            "/policies/reports",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"kind": str(kind)},
        )
        assert response.status_code == HTTP_CREATED
        assert response.json()["data"]["checksum_sha256"]

    async def test_a_report_can_be_downloaded(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        headers = auth_headers(CALLER)
        await make_policy("p1", PolicyEffect.DENY)
        created = await client.post(
            "/policies/reports",
            params=org(organization_id),
            headers=headers,
            json={"kind": str(ReportKind.POLICY)},
        )
        report_id = created.json()["data"]["id"]

        downloaded = await client.get(
            f"/policies/reports/{report_id}/download",
            params=org(organization_id),
            headers=headers,
        )
        assert downloaded.status_code == HTTP_OK
        assert json.loads(downloaded.content)["policies"]
        assert downloaded.headers["x-checksum-sha256"]

    async def test_another_organization_cannot_download_a_report(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A report payload can hold every decision an organization has
        # made, so the ownership check is the difference between a
        # download and a disclosure.
        headers = auth_headers(CALLER)
        await make_policy("p1", PolicyEffect.DENY)
        created = await client.post(
            "/policies/reports",
            params=org(organization_id),
            headers=headers,
            json={"kind": str(ReportKind.DECISION)},
        )
        report_id = created.json()["data"]["id"]

        stolen = await client.get(
            f"/policies/reports/{report_id}/download",
            params=org(uuid.uuid4()),
            headers=headers,
        )
        assert stolen.status_code == HTTP_NOT_FOUND

    async def test_the_audit_summary_counts_by_outcome(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        headers = auth_headers(CALLER)
        await make_policy("deny-platform", PolicyEffect.DENY)
        await client.post(
            "/policies/evaluate",
            params=org(organization_id),
            headers=headers,
            json=evaluate_body(),
        )
        summary = await client.get(
            "/policies/audit/summary", params=org(organization_id), headers=headers
        )
        assert summary.json()["data"]["denied"] >= 1

    async def test_the_attribute_catalogue_is_readable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/policies/attributes", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"] == []


class TestResponseEnvelope:
    """The platform's shared response shape."""

    async def test_a_success_carries_message_data_and_meta(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        payload = (
            await client.get("/policies", params=org(organization_id), headers=auth_headers(CALLER))
        ).json()
        assert payload["success"] is True
        assert payload["message"]
        assert "data" in payload
        assert "meta" in payload

    async def test_an_error_carries_a_platform_error_code(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        payload = (
            await client.get(
                f"/policies/{uuid.uuid4()}",
                params=org(organization_id),
                headers=auth_headers(CALLER),
            )
        ).json()
        assert payload["success"] is False
        assert payload["error"]["code"].startswith("AIIOS-")

    async def test_security_headers_are_applied(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        names = {name.lower() for name in response.headers}
        assert "x-content-type-options" in names


class TestTenantScoping:
    """One organization never reads another's governance."""

    async def test_another_organization_sees_no_policies(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("p1", PolicyEffect.DENY)
        response = await client.get(
            "/policies", params=org(uuid.uuid4()), headers=auth_headers(CALLER)
        )
        assert response.json()["data"] == []

    async def test_another_organizations_decisions_are_not_visible(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("deny-platform", PolicyEffect.DENY)
        await client.post(
            "/policies/evaluate",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json=evaluate_body(),
        )
        response = await client.get(
            "/policies/decisions", params=org(uuid.uuid4()), headers=auth_headers(CALLER)
        )
        assert response.json()["data"] == []

    async def test_another_organizations_audit_trail_is_not_visible(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("p1", PolicyEffect.DENY)
        await client.post(
            "/policies",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"slug": "p2", "name": "P2", "effect": str(PolicyEffect.ALLOW)},
        )
        response = await client.get(
            "/policies/audit", params=org(uuid.uuid4()), headers=auth_headers(CALLER)
        )
        assert response.json()["data"] == []

    async def test_a_decision_uses_only_its_own_organizations_catalogue(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # The one that matters most: a policy leaking across tenants would
        # mean one customer's governance silently deciding another's
        # requests.
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        response = await client.post(
            "/policies/evaluate",
            params=org(uuid.uuid4()),
            headers=auth_headers(CALLER),
            json=evaluate_body(),
        )
        assert response.json()["data"]["permitted"] is False
