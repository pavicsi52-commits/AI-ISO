"""Live lookups against the Playbook Service, backing docs/042
"PLAYBOOK INTEGRATION" "Integrate Prompt 041": Playbook Execution,
Template Execution, Version Resolution, Dependency Resolution.

Playbook *execution* still ultimately happens through
``services/automation-service`` (docs/041's own OBJECTIVE: "Execution
belongs to Prompt 040", never re-implemented here) -- this client only
resolves which content a ``TASK``/``CONNECTOR`` node's own
``playbook_id`` reference actually points at (its latest, or an
explicitly pinned, version) before that content is handed to
:class:`~app.clients.automation_client.AutomationClient` for dispatch.

"Dependency Resolution" is honestly NOT implemented here:
``services/playbook-service`` has a real
``PlaybookDependencyService``/``playbook_dependencies`` table but,
per its own README ("No REST surface for
categories/tags/labels/variables/dependencies/... as their own
top-level resources"), exposes no REST endpoint this client could call
-- the same "a required capability with no reachable endpoint on the
other side of the wire is an honest platform gap, not something to
fake" precedent every prior AI-IOS cross-service integration gap
(``services/automation-service``'s own schedule-fired-execution
caller-identity gap, its PLUGIN/AI node types being left unregistered)
already established.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


class PlaybookClient:
    """Resolves playbook/template/version references against the Playbook Service."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, caller_token: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def get_latest_version(self, playbook_id: UUID) -> dict[str, Any]:
        """Resolve *playbook_id*'s own current version content ("Version Resolution").

        Raises:
            DependencyError: If the Playbook Service is unreachable or
                *playbook_id* has no version yet.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/playbooks/{playbook_id}/versions", headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Playbook Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Playbook Service returned HTTP {response.status_code} "
                f"resolving playbook {playbook_id!r}."
            )
        versions = response.json()["data"]
        if not versions:
            raise DependencyError(f"Playbook {playbook_id!r} has no version yet.")
        return dict(versions[0])


__all__ = ["PlaybookClient"]
