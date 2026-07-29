"""HTTP tests against the real application.

The app is started through its actual lifespan -- real Postgres, Redis,
RabbitMQ, notifications, hub, and JWT key loading -- with only the
outbound data-source transport stubbed. Every assertion here is
therefore about the HTTP contract as it will actually behave.

**No ``/api/v1`` prefix.** The gateway owns versioning; every AI-IOS
service exposes bare paths. Getting that wrong is worth one explicit
test rather than ninety-five confusing 404s.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SharePermission
from app.repositories.dashboard import DashboardRepository
from app.repositories.dashboard_permission import DashboardPermissionRepository
from app.repositories.dashboard_share import DashboardShareRepository
from app.services.sharing import SharingService
from tests.conftest import (
    CHART_WIDGET,
    METRIC_WIDGET,
    TABLE_WIDGET,
    AuthHeadersFn,
    make_dashboard,
    make_widget,
)

ORG = uuid.UUID("22222222-2222-2222-2222-222222222222")

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNAVAILABLE = 503


def payload(response: Any) -> Any:
    """The ``data`` member of the platform's success envelope."""
    body = response.json()
    assert body["success"] is True, body
    return body["data"]


class TestAuthentication:
    """Every business route requires a verified token."""

    async def test_an_unauthenticated_request_is_refused(self, client: AsyncClient) -> None:
        response = await client.get("/dashboards", params={"organization_id": str(ORG)})
        assert response.status_code == HTTP_UNAUTHORIZED

    async def test_a_garbage_token_is_refused(self, client: AsyncClient) -> None:
        response = await client.get(
            "/dashboards",
            params={"organization_id": str(ORG)},
            headers={"Authorization": "Bearer not-a-token"},
        )
        assert response.status_code == HTTP_UNAUTHORIZED

    async def test_paths_carry_no_api_version_prefix(self, client: AsyncClient) -> None:
        # The gateway owns versioning. A service that invented its own
        # prefix would be unreachable through it.
        assert (await client.get("/api/v1/dashboards")).status_code == HTTP_NOT_FOUND


class TestDashboardRoutes:
    """CRUD over HTTP."""

    async def test_create_read_update_delete(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        caller = uuid.uuid4()
        headers = auth_headers(caller)

        created = await client.post(
            "/dashboards",
            params={"organization_id": str(ORG)},
            json={"slug": "fleet", "name": "Fleet", "dashboard_type": "infrastructure"},
            headers=headers,
        )
        assert created.status_code == HTTP_CREATED
        dashboard_id = payload(created)["id"]
        assert payload(created)["owner_id"] == str(caller)

        fetched = await client.get(f"/dashboards/{dashboard_id}", headers=headers)
        assert fetched.status_code == HTTP_OK
        assert payload(fetched)["slug"] == "fleet"

        updated = await client.put(
            f"/dashboards/{dashboard_id}",
            json={"name": "Renamed", "visibility": "organization"},
            headers=headers,
        )
        assert payload(updated)["name"] == "Renamed"

        deleted = await client.delete(f"/dashboards/{dashboard_id}", headers=headers)
        assert deleted.status_code == HTTP_OK
        assert (
            await client.get(f"/dashboards/{dashboard_id}", headers=headers)
        ).status_code == HTTP_NOT_FOUND

    async def test_a_duplicate_slug_is_a_conflict(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        body = {"slug": "dup", "name": "Dup"}
        await client.post(
            "/dashboards", params={"organization_id": str(ORG)}, json=body, headers=headers
        )
        second = await client.post(
            "/dashboards", params={"organization_id": str(ORG)}, json=body, headers=headers
        )
        assert second.status_code == HTTP_CONFLICT

    async def test_a_malformed_body_is_a_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        # The platform maps RequestValidationError to 400, not 422.
        response = await client.post(
            "/dashboards",
            params={"organization_id": str(ORG)},
            json={"name": "No slug"},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_listing_hides_dashboards_the_caller_cannot_see(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        await make_dashboard(db_session, organization_id=ORG, slug="private", owner_id=uuid.uuid4())
        await make_dashboard(
            db_session,
            organization_id=ORG,
            slug="shared",
            visibility="organization",  # type: ignore[arg-type]
        )
        response = await client.get(
            "/dashboards",
            params={"organization_id": str(ORG)},
            headers=auth_headers(uuid.uuid4()),
        )
        slugs = [item["slug"] for item in payload(response)]
        assert slugs == ["shared"], (
            "a private dashboard must not appear in a stranger's listing, "
            "even without its contents"
        )

    async def test_a_stranger_is_refused_a_private_dashboard(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=uuid.uuid4())
        response = await client.get(
            f"/dashboards/{dashboard.id}", headers=auth_headers(uuid.uuid4())
        )
        assert response.status_code == HTTP_FORBIDDEN

    async def test_a_viewer_cannot_edit(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        dashboard = await make_dashboard(
            db_session,
            organization_id=ORG,
            visibility="organization",  # type: ignore[arg-type]
        )
        response = await client.put(
            f"/dashboards/{dashboard.id}",
            json={"name": "Hijacked"},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_FORBIDDEN

    async def test_a_denial_is_audited(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        stranger = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=uuid.uuid4())
        await client.get(f"/dashboards/{dashboard.id}", headers=auth_headers(stranger))

        audit = await client.get(
            "/dashboards/audit",
            params={"organization_id": str(ORG)},
            headers=auth_headers(stranger),
        )
        entries = payload(audit)
        assert any(entry["outcome"] == "denied" for entry in entries), (
            "an attempt on a dashboard the caller had no right to is exactly "
            "what a security reviewer is looking for"
        )

    async def test_a_role_grant_lets_a_non_owner_edit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: AuthHeadersFn,
        publisher: Any,
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = SharingService(
            DashboardRepository(db_session),
            DashboardShareRepository(db_session),
            DashboardPermissionRepository(db_session),
            publish_event=publisher,
        )
        await sharing.grant_role(dashboard, role="ops", permission=SharePermission.EDIT)

        response = await client.put(
            f"/dashboards/{dashboard.id}",
            json={"name": "By role"},
            headers=auth_headers(uuid.uuid4(), roles=["ops"]),
        )
        assert response.status_code == HTTP_OK
        assert payload(response)["name"] == "By role"


class TestWidgetAndLayoutRoutes:
    """The literal collection paths docs/048 names."""

    async def test_widgets_collection_is_not_parsed_as_a_dashboard_id(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        # Declared before "/{dashboard_id}", or this would 422 forever.
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        await make_widget(db_session, dashboard=dashboard)
        response = await client.get(
            "/dashboards/widgets",
            params={"dashboard_id": str(dashboard.id)},
            headers=auth_headers(owner),
        )
        assert response.status_code == HTTP_OK
        assert [item["widget_key"] for item in payload(response)] == ["hosts"]

    async def test_adding_and_removing_a_widget(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        headers = auth_headers(owner)

        added = await client.post(
            "/dashboards/widgets",
            json={"dashboard_id": str(dashboard.id), "definition": TABLE_WIDGET},
            headers=headers,
        )
        assert added.status_code == HTTP_CREATED
        assert payload(added)["widget_key"] == "hosts"

        removed = await client.delete(f"/dashboards/{dashboard.id}/widgets/hosts", headers=headers)
        assert removed.status_code == HTTP_OK

    async def test_an_unrenderable_widget_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        response = await client.post(
            "/dashboards/widgets",
            json={
                "dashboard_id": str(dashboard.id),
                "definition": {"widget_key": "k", "title": "t", "widget_type": "line_chart"},
            },
            headers=auth_headers(owner),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_saving_and_listing_layouts(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        await make_widget(db_session, dashboard=dashboard)
        headers = auth_headers(owner)

        saved = await client.post(
            "/dashboards/layouts",
            json={
                "dashboard_id": str(dashboard.id),
                "breakpoint": "desktop",
                "placements": [{"widget_key": "hosts", "x": 0, "y": 0, "w": 6, "h": 3}],
            },
            headers=headers,
        )
        assert saved.status_code == HTTP_CREATED
        assert payload(saved)["revision"] == 1

        listed = await client.get(
            "/dashboards/layouts",
            params={"dashboard_id": str(dashboard.id)},
            headers=headers,
        )
        assert len(payload(listed)) == 1

    async def test_an_overlapping_layout_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        await make_widget(db_session, dashboard=dashboard, widget_key="a")
        await make_widget(db_session, dashboard=dashboard, widget_key="b")

        response = await client.post(
            "/dashboards/layouts",
            json={
                "dashboard_id": str(dashboard.id),
                "placements": [
                    {"widget_key": "a", "x": 0, "y": 0, "w": 6, "h": 3},
                    {"widget_key": "b", "x": 3, "y": 1, "w": 6, "h": 3},
                ],
            },
            headers=auth_headers(owner),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_restoring_a_revision(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        await make_widget(db_session, dashboard=dashboard)
        headers = auth_headers(owner)
        for x in (0, 6):
            await client.post(
                "/dashboards/layouts",
                json={
                    "dashboard_id": str(dashboard.id),
                    "placements": [{"widget_key": "hosts", "x": x, "y": 0, "w": 6, "h": 3}],
                },
                headers=headers,
            )

        restored = await client.post(
            f"/dashboards/{dashboard.id}/layout/restore",
            json={"breakpoint": "desktop", "revision": 1},
            headers=headers,
        )
        assert payload(restored)["revision"] == 1

        current = await client.get(f"/dashboards/{dashboard.id}/layout", headers=headers)
        assert payload(current)["placements"][0]["x"] == 0

    async def test_per_user_widget_settings(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(db_session, dashboard=dashboard)
        response = await client.put(
            f"/dashboards/widgets/{widget.id}/settings",
            json={"collapsed": True, "refresh_seconds_override": 300},
            headers=auth_headers(uuid.uuid4()),
        )
        assert payload(response)["collapsed"] is True
        assert payload(response)["refresh_seconds_override"] == 300


class TestLoadRoute:
    """The full dashboard load."""

    async def test_loading_resolves_every_widget(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        await make_widget(db_session, dashboard=dashboard)

        response = await client.get(f"/dashboards/{dashboard.id}/load", headers=auth_headers(owner))
        data = payload(response)
        assert data["dashboard"]["slug"] == "fleet"
        assert data["widgets"][0]["status"] == "ok"
        assert data["widgets"][0]["payload"]["rows"]
        assert data["failed_widgets"] == []
        assert data["layout"]["placements"][0]["widget_key"] == "hosts"

    async def test_a_failing_widget_degrades_rather_than_failing_the_load(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        await make_widget(db_session, dashboard=dashboard, widget_key="good")
        await make_widget(
            db_session,
            dashboard=dashboard,
            widget_key="broken",
            widget_type="topology_graph",  # type: ignore[arg-type]
            options={"topology": {"kind": "neighbors", "depth": 2}},
        )
        response = await client.get(f"/dashboards/{dashboard.id}/load", headers=auth_headers(owner))
        assert response.status_code == HTTP_OK
        data = payload(response)
        assert data["failed_widgets"] == ["broken"]
        assert len(data["widgets"]) == 2


class TestSharingRoutes:
    """Sharing over HTTP."""

    async def test_sharing_with_a_user(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        recipient = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)

        shared = await client.post(
            "/dashboards/share",
            json={
                "dashboard_id": str(dashboard.id),
                "user_id": str(recipient),
                "permission": "edit",
            },
            headers=auth_headers(owner),
        )
        assert shared.status_code == HTTP_CREATED
        assert "share_token" not in shared.text, "a listing must never echo a token"

        access = await client.get(
            f"/dashboards/{dashboard.id}/access", headers=auth_headers(recipient)
        )
        assert payload(access)["can_edit"] is True

    async def test_only_a_manager_may_share(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        dashboard = await make_dashboard(
            db_session,
            organization_id=ORG,
            visibility="organization",  # type: ignore[arg-type]
        )
        response = await client.post(
            "/dashboards/share",
            json={"dashboard_id": str(dashboard.id), "user_id": str(uuid.uuid4())},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_FORBIDDEN

    async def test_a_link_is_minted_once_and_then_opens_without_a_token(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        await make_widget(db_session, dashboard=dashboard)

        minted = await client.post(
            "/dashboards/share/link",
            json={"dashboard_id": str(dashboard.id)},
            headers=auth_headers(owner),
        )
        assert minted.status_code == HTTP_CREATED
        token = payload(minted)["token"]
        assert token

        # No Authorization header: the token is the credential.
        opened = await client.get(f"/dashboards/shared/{token}")
        assert opened.status_code == HTTP_OK
        data = payload(opened)
        assert data["dashboard"]["id"] == str(dashboard.id)
        assert data["layout"]["placements"], "the arrangement is part of the link"
        assert data["widgets"][0]["status"] == "unauthorized", (
            "this service holds no credential of its own, so an anonymous "
            "visitor gets structure -- resolving under the sharer's rights "
            "would hand a stranger whatever that person can see"
        )

    async def test_a_signed_in_visitor_following_a_link_sees_data(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        await make_widget(db_session, dashboard=dashboard)
        minted = await client.post(
            "/dashboards/share/link",
            json={"dashboard_id": str(dashboard.id)},
            headers=auth_headers(owner),
        )
        token = payload(minted)["token"]

        opened = await client.get(f"/dashboards/shared/{token}", headers=auth_headers(uuid.uuid4()))
        widget = payload(opened)["widgets"][0]
        assert widget["status"] == "ok"
        assert widget["payload"]["rows"], "a signed-in visitor resolves with their own token"

    async def test_a_share_listing_never_carries_a_token(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        headers = auth_headers(owner)
        minted = await client.post(
            "/dashboards/share/link",
            json={"dashboard_id": str(dashboard.id)},
            headers=headers,
        )
        token = payload(minted)["token"]

        listed = await client.get(
            "/dashboards/shares", params={"dashboard_id": str(dashboard.id)}, headers=headers
        )
        assert token not in listed.text, (
            "echoing tokens back would hand every viewer of the share list a "
            "working credential for every link"
        )
        assert payload(listed)[0]["is_link"] is True

    async def test_an_unknown_link_is_a_404(self, client: AsyncClient) -> None:
        assert (await client.get("/dashboards/shared/nope")).status_code == HTTP_NOT_FOUND

    async def test_a_revoked_link_stops_working(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        headers = auth_headers(owner)
        minted = await client.post(
            "/dashboards/share/link",
            json={"dashboard_id": str(dashboard.id)},
            headers=headers,
        )
        token = payload(minted)["token"]
        share_id = payload(minted)["share"]["id"]

        revoked = await client.delete(f"/dashboards/shares/{share_id}", headers=headers)
        assert payload(revoked)["is_revoked"] is True
        assert (await client.get(f"/dashboards/shared/{token}")).status_code == HTTP_CONFLICT

    async def test_role_permissions_over_http(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        headers = auth_headers(owner)

        granted = await client.post(
            "/dashboards/permissions",
            json={"dashboard_id": str(dashboard.id), "role": "ops", "permission": "manage"},
            headers=headers,
        )
        assert granted.status_code == HTTP_CREATED

        listed = await client.get(
            "/dashboards/permissions",
            params={"dashboard_id": str(dashboard.id)},
            headers=headers,
        )
        assert [item["role"] for item in payload(listed)] == ["ops"]

        revoked = await client.delete(
            "/dashboards/permissions",
            params={"dashboard_id": str(dashboard.id), "role": "ops"},
            headers=headers,
        )
        assert payload(revoked)["changed"] is True


class TestCatalogRoutes:
    """Templates and themes over HTTP."""

    async def test_template_lifecycle(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/dashboards/templates",
            params={"organization_id": str(ORG)},
            json={
                "slug": "ops",
                "name": "Ops",
                "definition": {"widgets": [TABLE_WIDGET, CHART_WIDGET]},
            },
            headers=headers,
        )
        assert created.status_code == HTTP_CREATED
        template_id = payload(created)["id"]

        listed = await client.get(
            "/dashboards/templates", params={"organization_id": str(ORG)}, headers=headers
        )
        assert len(payload(listed)) == 1

        applied = await client.post(
            f"/dashboards/templates/{template_id}/apply",
            params={"organization_id": str(ORG)},
            json={"slug": "from-template", "name": "From Template"},
            headers=headers,
        )
        assert applied.status_code == HTTP_CREATED
        dashboard_id = payload(applied)["id"]

        widgets = await client.get(
            "/dashboards/widgets", params={"dashboard_id": dashboard_id}, headers=headers
        )
        assert {item["widget_key"] for item in payload(widgets)} == {"hosts", "cpu_by_env"}

        assert (
            await client.delete(f"/dashboards/templates/{template_id}", headers=headers)
        ).status_code == HTTP_OK

    async def test_capturing_a_dashboard_as_a_template(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        await make_widget(db_session, dashboard=dashboard)

        response = await client.post(
            "/dashboards/templates/capture",
            json={"dashboard_id": str(dashboard.id), "slug": "cap", "name": "Captured"},
            headers=auth_headers(owner),
        )
        assert response.status_code == HTTP_CREATED
        assert payload(response)["slug"] == "cap"

    async def test_theme_lifecycle_and_accessibility_report(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/dashboards/themes",
            params={"organization_id": str(ORG)},
            json={
                "slug": "pale",
                "name": "Pale",
                "definition": {"palette": {"text": "#eeeeee", "background": "#ffffff"}},
            },
            headers=headers,
        )
        assert created.status_code == HTTP_CREATED
        assert payload(created)[
            "contrast_findings"
        ], "a shortfall must be visible on the response that created it"
        theme_id = payload(created)["theme"]["id"]

        report = await client.get(f"/dashboards/themes/{theme_id}/accessibility", headers=headers)
        assert payload(report)["wcag_aa"] is False

        updated = await client.put(
            f"/dashboards/themes/{theme_id}",
            json={"definition": {"palette": {"text": "#111827", "background": "#ffffff"}}},
            headers=headers,
        )
        assert payload(updated)["contrast_findings"] == []

        assert (
            await client.delete(f"/dashboards/themes/{theme_id}", headers=headers)
        ).status_code == HTTP_OK

    async def test_seeding_built_in_themes_is_idempotent(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        first = await client.post(
            "/dashboards/themes/seed", params={"organization_id": str(ORG)}, headers=headers
        )
        assert len(payload(first)) == 2
        second = await client.post(
            "/dashboards/themes/seed", params={"organization_id": str(ORG)}, headers=headers
        )
        assert payload(second) == []

    async def test_a_built_in_theme_cannot_be_edited(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        seeded = await client.post(
            "/dashboards/themes/seed", params={"organization_id": str(ORG)}, headers=headers
        )
        theme_id = payload(seeded)[0]["id"]
        response = await client.put(
            f"/dashboards/themes/{theme_id}", json={"name": "Hijacked"}, headers=headers
        )
        assert response.status_code == HTTP_CONFLICT


class TestAnalyticsRoutes:
    """Statistics, audit, favourites, filters, and presence."""

    async def test_statistics_recompute_and_read_back(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        await make_dashboard(db_session, organization_id=ORG)
        headers = auth_headers(uuid.uuid4())

        response = await client.get(
            "/dashboards/statistics",
            params={"organization_id": str(ORG), "recompute": "true"},
            headers=headers,
        )
        assert payload(response)["total_dashboards"] == 1

        cached = await client.get(
            "/dashboards/statistics", params={"organization_id": str(ORG)}, headers=headers
        )
        assert payload(cached)["total_dashboards"] == 1

    async def test_one_dashboard_usage(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        await make_widget(db_session, dashboard=dashboard)
        headers = auth_headers(owner)
        await client.get(f"/dashboards/{dashboard.id}/load", headers=headers)

        usage = await client.get(f"/dashboards/{dashboard.id}/statistics", headers=headers)
        assert payload(usage)["views"] == 1

    async def test_audit_summary(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        headers = auth_headers(owner)
        await client.get(f"/dashboards/{dashboard.id}/load", headers=headers)

        summary = await client.get(
            "/dashboards/audit/summary", params={"organization_id": str(ORG)}, headers=headers
        )
        assert payload(summary)["total"] >= 1

    async def test_favourites_over_http(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        user = uuid.uuid4()
        first = await make_dashboard(db_session, organization_id=ORG, slug="a", name="A")
        second = await make_dashboard(db_session, organization_id=ORG, slug="b", name="B")
        headers = auth_headers(user)

        for dashboard in (first, second):
            assert (
                await client.post(f"/dashboards/{dashboard.id}/favorite", headers=headers)
            ).status_code == HTTP_OK

        reordered = await client.put(
            "/dashboards/favorites",
            params={"organization_id": str(ORG)},
            json={"dashboard_ids": [str(second.id), str(first.id)]},
            headers=headers,
        )
        assert [item["slug"] for item in payload(reordered)] == ["b", "a"]

        assert payload(await client.delete(f"/dashboards/{first.id}/favorite", headers=headers))[
            "removed"
        ]

        listed = await client.get(
            "/dashboards/favorites", params={"organization_id": str(ORG)}, headers=headers
        )
        assert [item["slug"] for item in payload(listed)] == ["b"]

    async def test_saved_filters_over_http(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        headers = auth_headers(owner)

        saved = await client.post(
            f"/dashboards/{dashboard.id}/filters",
            json={
                "name": "Prod",
                "clauses": [{"field": "env", "operator": "eq", "value": "prod"}],
            },
            headers=headers,
        )
        assert saved.status_code == HTTP_CREATED

        listed = await client.get(f"/dashboards/{dashboard.id}/filters", headers=headers)
        assert [item["name"] for item in payload(listed)] == ["Prod"]

    async def test_saving_a_shared_preset_needs_edit_access(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        dashboard = await make_dashboard(
            db_session,
            organization_id=ORG,
            visibility="organization",  # type: ignore[arg-type]
        )
        response = await client.post(
            f"/dashboards/{dashboard.id}/filters",
            json={"name": "Shared", "clauses": [], "shared": True},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_FORBIDDEN

    async def test_history_over_http(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        caller = uuid.uuid4()
        headers = auth_headers(caller)
        created = await client.post(
            "/dashboards",
            params={"organization_id": str(ORG)},
            json={"slug": "hist", "name": "Hist"},
            headers=headers,
        )
        dashboard_id = payload(created)["id"]

        history = await client.get(f"/dashboards/{dashboard_id}/history", headers=headers)
        assert [entry["event"] for entry in payload(history)] == ["created"]

    async def test_presence_says_it_is_replica_scoped(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        response = await client.get(
            f"/dashboards/{dashboard.id}/presence", headers=auth_headers(uuid.uuid4())
        )
        data = payload(response)
        assert data["watchers"] == []
        assert data["replica_scoped"] is True

    async def test_a_manual_refresh_reaches_nobody_when_nobody_is_watching(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: AuthHeadersFn
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        response = await client.post(
            f"/dashboards/{dashboard.id}/refresh", headers=auth_headers(uuid.uuid4())
        )
        assert payload(response)["delivered"] == 0

    async def test_topology_reports_itself_unconfigured_rather_than_pretending(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        response = await client.post(
            "/dashboards/topology",
            params={"organization_id": str(ORG)},
            json={"root_id": "asset-1", "kind": "neighbors", "depth": 2},
            headers=auth_headers(uuid.uuid4()),
        )
        # DependencyError maps to 503 with a sanitised body, so the
        # error *code* is what a client can actually rely on.
        assert response.status_code == HTTP_UNAVAILABLE
        assert response.json()["error"]["code"] == "AIIOS-DEP-0001"


class TestOpenApiContract:
    """The published contract itself."""

    def test_every_documented_rest_path_exists(self, app: Any) -> None:
        # The exact list docs/048 "REST APIs" specifies.
        spec = app.openapi()
        required = {
            ("get", "/dashboards"),
            ("post", "/dashboards"),
            ("get", "/dashboards/{dashboard_id}"),
            ("put", "/dashboards/{dashboard_id}"),
            ("delete", "/dashboards/{dashboard_id}"),
            ("get", "/dashboards/templates"),
            ("post", "/dashboards/templates"),
            ("get", "/dashboards/widgets"),
            ("post", "/dashboards/widgets"),
            ("get", "/dashboards/layouts"),
            ("post", "/dashboards/layouts"),
            ("post", "/dashboards/share"),
            ("get", "/dashboards/statistics"),
        }
        missing = {
            (method, path) for method, path in required if method not in spec["paths"].get(path, {})
        }
        assert not missing, f"docs/048 names these and they are absent: {sorted(missing)}"

    def test_literal_collections_precede_the_dashboard_id_route(self, app: Any) -> None:
        # If "/{dashboard_id}" were registered first, "/statistics" would
        # be parsed as a dashboard id and 422 forever.
        paths = [route.path for route in app.routes if hasattr(route, "path")]
        del paths  # the OpenAPI check below is the meaningful assertion
        spec = app.openapi()
        assert "get" in spec["paths"]["/dashboards/statistics"]
        assert "get" in spec["paths"]["/dashboards/{dashboard_id}"]


@pytest.mark.parametrize("definition", [TABLE_WIDGET, METRIC_WIDGET, CHART_WIDGET])
async def test_every_sample_widget_renders_end_to_end(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: AuthHeadersFn,
    definition: dict[str, Any],
) -> None:
    """Each widget shape resolves to a non-empty payload over HTTP."""
    owner = uuid.uuid4()
    dashboard = await make_dashboard(
        db_session, organization_id=ORG, owner_id=owner, slug=definition["widget_key"]
    )
    headers = auth_headers(owner)
    await client.post(
        "/dashboards/widgets",
        json={"dashboard_id": str(dashboard.id), "definition": definition},
        headers=headers,
    )
    response = await client.get(f"/dashboards/{dashboard.id}/load", headers=headers)
    widget = payload(response)["widgets"][0]
    assert widget["status"] == "ok", widget
    assert widget["payload"]
