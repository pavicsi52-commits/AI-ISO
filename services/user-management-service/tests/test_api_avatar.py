"""HTTP-level tests for POST/DELETE /users/avatar."""

from __future__ import annotations

import io
import uuid
from collections.abc import Callable

from httpx import AsyncClient
from PIL import Image


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


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color="green").save(buffer, format="PNG")
    return buffer.getvalue()


async def test_upload_and_delete_avatar(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    user_id, headers = await _create_caller(client, auth_headers)

    uploaded = await client.post(
        "/users/avatar",
        headers=headers,
        files={"file": ("avatar.png", _png_bytes(), "image/png")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["data"]["url"].startswith("http")

    profile = await client.get(f"/users/{user_id}", headers=headers)
    assert profile.json()["data"]["avatar"] is not None

    deleted = await client.delete("/users/avatar", headers=headers)
    assert deleted.status_code == 200


async def test_upload_avatar_rejects_non_image(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)

    response = await client.post(
        "/users/avatar",
        headers=headers,
        files={"file": ("a.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 400


async def test_avatar_endpoints_require_authentication(client: AsyncClient) -> None:
    response = await client.delete("/users/avatar")

    assert response.status_code == 401
