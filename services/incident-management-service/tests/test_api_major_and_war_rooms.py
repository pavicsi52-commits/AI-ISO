"""HTTP tests for /major-incidents and /war-rooms routes."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import HTTP_BAD_REQUEST, HTTP_CONFLICT, HTTP_CREATED, HTTP_OK

pytestmark = pytest.mark.asyncio


async def _open_incident(client: AsyncClient, headers: dict[str, str], organization_id) -> dict:
    resp = await client.post(
        "/incidents",
        params={"organization_id": str(organization_id)},
        headers=headers,
        json={"title": "Estate-wide outage"},
    )
    assert resp.status_code == HTTP_CREATED
    return resp.json()["data"]


async def _declare_major(
    client: AsyncClient, headers: dict[str, str], organization_id, incident_id: str
) -> dict:
    resp = await client.post(
        f"/major-incidents/{incident_id}/declare",
        params={"organization_id": str(organization_id)},
        headers=headers,
        json={"reason": "Estate-wide outage", "incident_commander_id": "alice"},
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestDeclareAndList:
    async def test_declare_returns_the_declaration(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        declared = await _declare_major(client, headers, organization_id, incident["id"])
        assert declared["incident_commander_id"] == "alice"

    async def test_list_active_finds_it(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        declared = await _declare_major(client, headers, organization_id, incident["id"])
        resp = await client.get(
            "/major-incidents", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert declared["id"] in {one["id"] for one in resp.json()["data"]}

    async def test_get_by_incident_finds_the_declaration(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _declare_major(client, headers, organization_id, incident["id"])
        resp = await client.get(
            f"/major-incidents/{incident['id']}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] is not None

    async def test_get_by_incident_is_null_when_never_declared(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        resp = await client.get(
            f"/major-incidents/{incident['id']}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] is None


class TestStatusUpdateAndClosure:
    async def test_status_update_records_the_summary(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        declared = await _declare_major(client, headers, organization_id, incident["id"])
        resp = await client.post(
            f"/major-incidents/{declared['id']}/status-update",
            params={"organization_id": str(organization_id)},
            json={"summary": "Still investigating."},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["executive_summary"] == "Still investigating."

    async def test_approve_closure_before_resolution_is_refused(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        declared = await _declare_major(client, headers, organization_id, incident["id"])
        resp = await client.post(
            f"/major-incidents/{declared['id']}/approve-closure",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"approved_by": "director-1"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


async def _war_room_for(client: AsyncClient, organization_id, incident_id: str) -> dict:
    resp = await client.get(
        f"/major-incidents/{incident_id}/war-room",
        params={"organization_id": str(organization_id)},
    )
    assert resp.status_code == HTTP_OK, resp.text
    data = resp.json()["data"]
    assert data is not None
    return data


class TestWarRooms:
    async def test_get_war_room_for_incident(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _declare_major(client, headers, organization_id, incident["id"])
        war_room = await _war_room_for(client, organization_id, incident["id"])
        assert war_room["status"] == "open"

    async def test_get_war_room_directly_by_id(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _declare_major(client, headers, organization_id, incident["id"])
        war_room = await _war_room_for(client, organization_id, incident["id"])
        resp = await client.get(
            f"/war-rooms/{war_room['id']}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == war_room["id"]

    async def test_the_commander_is_seated_automatically(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _declare_major(client, headers, organization_id, incident["id"])
        war_room = await _war_room_for(client, organization_id, incident["id"])
        resp = await client.get(
            f"/war-rooms/{war_room['id']}/participants",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        roles = {one["role"] for one in resp.json()["data"]}
        assert "incident_commander" in roles

    async def test_add_participant_and_singleton_role_conflict(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _declare_major(client, headers, organization_id, incident["id"])
        war_room = await _war_room_for(client, organization_id, incident["id"])
        added = await client.post(
            f"/war-rooms/{war_room['id']}/participants",
            params={"organization_id": str(organization_id)},
            json={"participant_id": "bob", "role": "technical_lead"},
        )
        assert added.status_code == HTTP_CREATED
        conflict = await client.post(
            f"/war-rooms/{war_room['id']}/participants",
            params={"organization_id": str(organization_id)},
            json={"participant_id": "carol", "role": "technical_lead"},
        )
        assert conflict.status_code == HTTP_CONFLICT

    async def test_leave_marks_the_participant_left(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _declare_major(client, headers, organization_id, incident["id"])
        war_room = await _war_room_for(client, organization_id, incident["id"])
        resp = await client.post(
            f"/war-rooms/{war_room['id']}/leave",
            params={"organization_id": str(organization_id)},
            json={"participant_id": "alice"},
        )
        assert resp.status_code == HTTP_OK

    async def test_add_shared_note_appends(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _declare_major(client, headers, organization_id, incident["id"])
        war_room = await _war_room_for(client, organization_id, incident["id"])
        resp = await client.post(
            f"/war-rooms/{war_room['id']}/notes",
            params={"organization_id": str(organization_id)},
            json={"note": "Investigating."},
        )
        assert resp.status_code == HTTP_OK
        assert "Investigating." in resp.json()["data"]["shared_notes"]

    async def test_stand_down_closes_it(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _declare_major(client, headers, organization_id, incident["id"])
        war_room = await _war_room_for(client, organization_id, incident["id"])
        resp = await client.post(
            f"/war-rooms/{war_room['id']}/stand-down",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "closed"
