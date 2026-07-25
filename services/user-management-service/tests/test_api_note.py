"""HTTP-level tests for POST/GET/DELETE /users/{user_id}/notes."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def _create_caller(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> tuple[uuid.UUID, dict[str, str]]:
    admin_headers = auth_headers(uuid.uuid4())
    response = await client.post(
        "/users",
        headers=admin_headers,
        json={
            "username": f"user-{uuid.uuid4().hex[:12]}",
            "email": f"user-{uuid.uuid4().hex}@example.com",
        },
    )
    assert response.status_code == 201, response.text
    user_id = uuid.UUID(response.json()["data"]["id"])
    return user_id, auth_headers(user_id)


async def test_add_list_remove_note(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    subject_id, _subject_headers = await _create_caller(client, auth_headers)
    _author_id, author_headers = await _create_caller(client, auth_headers)

    created = await client.post(
        f"/users/{subject_id}/notes", headers=author_headers, json={"body": "Escalated to manager."}
    )
    assert created.status_code == 201
    assert created.json()["data"]["author_id"] == str(_author_id)
    note_id = created.json()["data"]["id"]

    listed = await client.get(f"/users/{subject_id}/notes", headers=author_headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1
    assert listed.json()["data"][0]["body"] == "Escalated to manager."

    removed = await client.delete(f"/users/{subject_id}/notes/{note_id}", headers=author_headers)
    assert removed.status_code == 200

    after_delete = await client.get(f"/users/{subject_id}/notes", headers=author_headers)
    assert after_delete.json()["data"] == []


async def test_note_endpoints_require_authentication(client: AsyncClient) -> None:
    response = await client.get(f"/users/{uuid.uuid4()}/notes")

    assert response.status_code == 401


async def test_remove_note_for_wrong_subject_returns_404(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    subject_id, _subject_headers = await _create_caller(client, auth_headers)
    other_subject_id, _other_headers = await _create_caller(client, auth_headers)
    _author_id, author_headers = await _create_caller(client, auth_headers)
    created = await client.post(
        f"/users/{subject_id}/notes", headers=author_headers, json={"body": "About subject 1."}
    )
    note_id = created.json()["data"]["id"]

    response = await client.delete(
        f"/users/{other_subject_id}/notes/{note_id}", headers=author_headers
    )

    assert response.status_code == 404
