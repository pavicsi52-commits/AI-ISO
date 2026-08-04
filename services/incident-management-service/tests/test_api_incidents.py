"""HTTP tests for /incidents, SLA, escalation, and impact routes.

Against the real built app, over its actual lifespan -- see
``tests/conftest.py`` for why only the request session is overridden,
and what that override cannot tell us.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CONFLICT,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


async def _open_incident(
    client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID, **overrides
) -> dict:
    payload = {"title": "Disk full on host-1", "priority": "p2_high", **overrides}
    resp = await client.post(
        "/incidents",
        params={"organization_id": str(organization_id)},
        headers=headers,
        json=payload,
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestCreateAndList:
    async def test_create_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/incidents",
            params={"organization_id": str(organization_id)},
            json={"title": "x"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_incident(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        data = await _open_incident(client, headers, organization_id)
        assert data["reference"].startswith("INC-")
        assert data["status"] == "new"

    async def test_list_finds_the_created_incident(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        resp = await client.get(
            "/incidents", params={"organization_id": str(organization_id)}, headers=headers
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_get_returns_404_for_a_missing_incident(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/incidents/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestTransitionAssignMerge:
    async def test_transition_moves_status(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        resp = await client.put(
            f"/incidents/{created['id']}/transition",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"status": "assigned"},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "assigned"

    async def test_illegal_transition_returns_400(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        resp = await client.put(
            f"/incidents/{created['id']}/transition",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"status": "resolved"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_assign_sets_the_assignee(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        resp = await client.post(
            f"/incidents/{created['id']}/assign",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"assignee_id": "alice"},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["assignee_id"] == "alice"

    async def test_auto_assign_chooses_from_the_roster(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        resp = await client.post(
            f"/incidents/{created['id']}/auto-assign",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"roster": [{"responder_id": "bob", "is_on_call": True}]},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["assignee_id"] == "bob"

    async def test_merge_moves_the_source_to_merged(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        source = await _open_incident(client, headers, organization_id, title="Dup")
        target = await _open_incident(client, headers, organization_id, title="Original")
        resp = await client.post(
            f"/incidents/{source['id']}/merge",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"target_incident_id": target["id"], "reason": "same root cause"},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "merged"


class TestTimelineWorklogNotes:
    async def test_timeline_starts_with_the_open_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        resp = await client.get(
            f"/incidents/{created['id']}/timeline",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert len(resp.json()["data"]) == 1

    async def test_add_note_appends_to_timeline(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        resp = await client.post(
            f"/incidents/{created['id']}/notes",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"summary": "Checked in with vendor."},
        )
        assert resp.status_code == HTTP_CREATED
        timeline = await client.get(
            f"/incidents/{created['id']}/timeline",
            params={"organization_id": str(organization_id)},
        )
        assert len(timeline.json()["data"]) == 2

    async def test_add_and_list_worklog(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        resp = await client.post(
            f"/incidents/{created['id']}/worklog",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"note": "Investigated logs", "minutes_spent": 15},
        )
        assert resp.status_code == HTTP_CREATED
        listed = await client.get(
            f"/incidents/{created['id']}/worklog",
            params={"organization_id": str(organization_id)},
        )
        assert len(listed.json()["data"]) == 1


class TestSla:
    async def test_list_slas_is_empty_until_started(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        resp = await client.get(
            f"/incidents/{created['id']}/slas", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_pause_a_missing_sla_returns_404(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/incidents/slas/{uuid.uuid4()}/pause",
            params={"organization_id": str(organization_id)},
            json={"reason": "waiting"},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestEscalation:
    async def test_escalate_manually_creates_a_triggered_escalation(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        resp = await client.post(
            f"/incidents/{created['id']}/escalate",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"target_id": "director-1", "reason": "Executive visibility"},
        )
        assert resp.status_code == HTTP_CREATED
        assert resp.json()["data"]["status"] == "triggered"

    async def test_list_escalations_finds_it(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        await client.post(
            f"/incidents/{created['id']}/escalate",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"target_id": "director-1", "reason": "visibility"},
        )
        resp = await client.get(
            f"/incidents/{created['id']}/escalations",
            params={"organization_id": str(organization_id)},
        )
        assert len(resp.json()["data"]) == 1

    async def test_acknowledge_then_cancel_conflicts(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        escalated = await client.post(
            f"/incidents/{created['id']}/escalate",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"target_id": "director-1", "reason": "visibility"},
        )
        escalation_id = escalated.json()["data"]["id"]
        ack = await client.post(
            f"/incidents/escalations/{escalation_id}/acknowledge",
            params={"organization_id": str(organization_id)},
        )
        assert ack.status_code == HTTP_OK
        cancel = await client.post(
            f"/incidents/escalations/{escalation_id}/cancel",
            params={"organization_id": str(organization_id)},
            json={"reason": "too late"},
        )
        assert cancel.status_code == HTTP_CONFLICT


class TestImpact:
    async def test_assess_and_read_history(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _open_incident(client, headers, organization_id)
        resp = await client.post(
            f"/incidents/{created['id']}/impact",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={
                "services": [{"service_name": "checkout", "impact_level": "severe"}],
                "customer_impact": "major",
            },
        )
        assert resp.status_code == HTTP_CREATED
        assert resp.json()["data"]["topology_impact"] == "severe"
        history = await client.get(
            f"/incidents/{created['id']}/impact",
            params={"organization_id": str(organization_id)},
        )
        assert len(history.json()["data"]) == 1
