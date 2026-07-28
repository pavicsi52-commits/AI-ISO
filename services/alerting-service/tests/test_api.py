"""API-layer tests, exercised through the real app and its own full
lifespan (real Postgres/Redis/RabbitMQ, real SchedulerManager).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AlertStatus
from tests.conftest import (
    AuthHeadersFn,
    make_alert,
    make_escalation_policy,
    make_suppression,
)


def _org_params(org: uuid.UUID) -> dict[str, str]:
    return {"organization_id": str(org)}


class TestAlertsApi:
    async def test_create_runs_the_full_pipeline(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org = uuid.uuid4()
        response = await client.post(
            "/alerts",
            json={
                "organization_id": str(org),
                "source": "monitoring",
                "severity": "high",
                "title": "Disk full",
                "message": "/var at 98%",
                "source_reference": {"target_id": "db-1"},
            },
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["status"] == "open"
        assert body["message"] == "Alert created."

    async def test_duplicate_create_is_reported_as_deduplicated(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        payload = {
            "organization_id": str(org),
            "source": "monitoring",
            "severity": "high",
            "title": "Disk full",
            "message": "/var at 98%",
            "source_reference": {"target_id": "db-1"},
        }
        first = await client.post("/alerts", json=payload, headers=headers)
        second = await client.post("/alerts", json=payload, headers=headers)
        assert second.json()["message"] == "Alert deduplicated."
        assert second.json()["data"]["id"] == first.json()["data"]["id"]

    async def test_suppressed_create_is_reported_as_suppressed(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        db_session: AsyncSession,
    ) -> None:
        org = uuid.uuid4()
        await make_suppression(db_session, organization_id=org)
        response = await client.post(
            "/alerts",
            json={
                "organization_id": str(org),
                "source": "monitoring",
                "severity": "high",
                "title": "t",
                "message": "m",
                "source_reference": {"target_id": "db-1"},
            },
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.json()["message"] == "Alert suppressed."
        assert response.json()["data"]["status"] == "suppressed"

    async def test_list_and_get(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        alert = await make_alert(db_session, organization_id=org)
        headers = auth_headers(uuid.uuid4())

        listed = await client.get("/alerts", params=_org_params(org), headers=headers)
        assert listed.status_code == 200
        assert len(listed.json()["data"]) == 1

        fetched = await client.get(f"/alerts/{alert.id}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["data"]["id"] == str(alert.id)

    async def test_list_filters_by_status(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        await make_alert(db_session, organization_id=org, status=AlertStatus.OPEN)
        await make_alert(db_session, organization_id=org, status=AlertStatus.RESOLVED)
        response = await client.get(
            "/alerts",
            params={"organization_id": str(org), "status": "open"},
            headers=auth_headers(uuid.uuid4()),
        )
        assert len(response.json()["data"]) == 1

    async def test_get_unknown_alert_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        response = await client.get(f"/alerts/{uuid.uuid4()}", headers=auth_headers(uuid.uuid4()))
        assert response.status_code == 404

    async def test_update_alert(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        alert = await make_alert(db_session)
        response = await client.put(
            f"/alerts/{alert.id}",
            json={"severity": "critical", "title": "escalating"},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == 200
        assert response.json()["data"]["severity"] == "critical"

    async def test_acknowledge_resolve_flow(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        alert = await make_alert(db_session, status=AlertStatus.OPEN)
        headers = auth_headers(uuid.uuid4())

        acked = await client.post(
            f"/alerts/{alert.id}/acknowledge", json={"comment": "on it"}, headers=headers
        )
        assert acked.json()["data"]["status"] == "acknowledged"

        resolved = await client.post(
            f"/alerts/{alert.id}/resolve",
            json={"resolution_notes": "restarted"},
            headers=headers,
        )
        assert resolved.json()["data"]["status"] == "resolved"

        acknowledgements = await client.get(f"/alerts/{alert.id}/acknowledgements", headers=headers)
        assert len(acknowledgements.json()["data"]) == 2

    async def test_invalid_transition_returns_conflict(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        alert = await make_alert(db_session, status=AlertStatus.CLOSED)
        response = await client.post(
            f"/alerts/{alert.id}/acknowledge", json={}, headers=auth_headers(uuid.uuid4())
        )
        assert response.status_code == 409

    async def test_escalate_with_policy(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        policy = await make_escalation_policy(db_session, organization_id=org)
        alert = await make_alert(db_session, organization_id=org, status=AlertStatus.OPEN)
        response = await client.post(
            f"/alerts/{alert.id}/escalate",
            json={"policy_id": str(policy.id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "escalated"

    async def test_delete_closes_rather_than_removes(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        """An alert is an operational record; closing preserves history."""
        alert = await make_alert(db_session, status=AlertStatus.RESOLVED)
        headers = auth_headers(uuid.uuid4())
        deleted = await client.delete(f"/alerts/{alert.id}", headers=headers)
        assert deleted.json()["data"]["status"] == "closed"

        still_there = await client.get(f"/alerts/{alert.id}", headers=headers)
        assert still_there.status_code == 200

    async def test_history_notifications_and_correlations(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        alert = await make_alert(db_session, status=AlertStatus.OPEN)
        headers = auth_headers(uuid.uuid4())
        await client.post(f"/alerts/{alert.id}/acknowledge", json={}, headers=headers)

        history = await client.get(f"/alerts/{alert.id}/history", headers=headers)
        assert history.status_code == 200
        assert len(history.json()["data"]) >= 1

        notifications = await client.get(f"/alerts/{alert.id}/notifications", headers=headers)
        assert notifications.status_code == 200

        correlations = await client.get(f"/alerts/{alert.id}/correlations", headers=headers)
        assert correlations.status_code == 200

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get("/alerts", params=_org_params(uuid.uuid4()))).status_code == 401


class TestAlertRulesApi:
    async def test_create_then_list_with_conditions(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/alert-rules",
            json={
                "organization_id": str(org),
                "name": "cpu-high",
                "rule_type": "metric_threshold",
                "source": "monitoring",
                "severity": "high",
                "conditions": [{"sequence": 0, "expression": "value > 90"}],
            },
            headers=headers,
        )
        assert created.status_code == 201
        assert len(created.json()["data"]["conditions"]) == 1

        listed = await client.get("/alert-rules", params=_org_params(org), headers=headers)
        assert len(listed.json()["data"]) == 1

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get("/alert-rules", params=_org_params(uuid.uuid4()))
        assert response.status_code == 401


class TestMaintenanceWindowsApi:
    async def test_create_then_list_active(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        now = datetime.now(UTC)
        created = await client.post(
            "/maintenance-windows",
            json={
                "organization_id": str(org),
                "name": "patching",
                "window_type": "scheduled",
                "scope": "organization",
                "starts_at": (now - timedelta(minutes=5)).isoformat(),
                "ends_at": (now + timedelta(hours=1)).isoformat(),
            },
            headers=headers,
        )
        assert created.status_code == 201

        active = await client.get(
            "/maintenance-windows",
            params={"organization_id": str(org), "active_only": "true"},
            headers=headers,
        )
        assert len(active.json()["data"]) == 1

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get("/maintenance-windows", params=_org_params(uuid.uuid4()))
        assert response.status_code == 401


class TestOnCallSchedulesApi:
    async def test_create_then_read_current(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/oncall-schedules",
            json={
                "organization_id": str(org),
                "name": "primary",
                "rotation_type": "weekly",
                "participants": ["u1", "u2"],
            },
            headers=headers,
        )
        assert created.status_code == 201
        schedule_id = created.json()["data"]["id"]

        current = await client.get(f"/oncall-schedules/{schedule_id}/current", headers=headers)
        assert current.json()["data"]["user_id"] == "u1"

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get("/oncall-schedules", params=_org_params(uuid.uuid4()))
        assert response.status_code == 401


class TestConfigurationApis:
    async def test_route_create_then_list(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/alert-routes",
            json={
                "organization_id": str(org),
                "name": "oncall-email",
                "channel": "email",
                "target_type": "user",
                "target_reference": "user@example.internal",
                "severity_filter": "high",
            },
            headers=headers,
        )
        assert created.status_code == 201

        listed = await client.get("/alert-routes", params=_org_params(org), headers=headers)
        assert len(listed.json()["data"]) == 1

    async def test_escalation_policy_returns_validated_levels(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/alert-escalation-policies",
            json={
                "organization_id": str(org),
                "name": "standard",
                "levels": [
                    {"target_type": "user", "target_reference": "u1", "delay_seconds": 300},
                    {"target_type": "manager", "target_reference": "m1", "delay_seconds": 600},
                ],
            },
            headers=headers,
        )
        assert created.status_code == 201
        levels = created.json()["data"]["levels"]
        assert [level["cumulative_delay_seconds"] for level in levels] == [300.0, 900.0]

        listed = await client.get(
            "/alert-escalation-policies", params=_org_params(org), headers=headers
        )
        assert len(listed.json()["data"]) == 1

    async def test_suppression_create_then_list(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/alert-suppressions",
            json={
                "organization_id": str(org),
                "suppression_type": "temporary",
                "scope_reference": "db-1",
                "starts_at": datetime.now(UTC).isoformat(),
            },
            headers=headers,
        )
        assert created.status_code == 201

        listed = await client.get("/alert-suppressions", params=_org_params(org), headers=headers)
        assert len(listed.json()["data"]) == 1

    async def test_all_three_require_authentication(self, client: AsyncClient) -> None:
        params = _org_params(uuid.uuid4())
        for path in ("/alert-routes", "/alert-escalation-policies", "/alert-suppressions"):
            assert (await client.get(path, params=params)).status_code == 401


class TestAnalyticsApis:
    async def test_statistics_for_empty_org(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        response = await client.get(
            "/alert-statistics",
            params=_org_params(uuid.uuid4()),
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == 200
        assert response.json()["data"]["total_alerts"] == 0

    async def test_statistics_recompute(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        await make_alert(db_session, organization_id=org)
        response = await client.get(
            "/alert-statistics",
            params={"organization_id": str(org), "recompute": "true"},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.json()["data"]["total_alerts"] == 1

    async def test_generate_then_list_report(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/alert-reports",
            json={"organization_id": str(org), "report_type": "executive"},
            headers=headers,
        )
        assert created.status_code == 201

        listed = await client.get("/alert-reports", params=_org_params(org), headers=headers)
        assert len(listed.json()["data"]) == 1

    async def test_alert_report_without_id_is_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        """400, not 422: this is a business-rule ``ValidationError`` raised
        by the service, which ``shared_core``'s own exception handler maps
        to 400 -- 422 is FastAPI's own schema-level rejection, and the
        request body here is schema-valid.
        """
        response = await client.post(
            "/alert-reports",
            json={"organization_id": str(uuid.uuid4()), "report_type": "alert"},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == 400

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        params = _org_params(uuid.uuid4())
        assert (await client.get("/alert-statistics", params=params)).status_code == 401
        assert (await client.get("/alert-reports", params=params)).status_code == 401
