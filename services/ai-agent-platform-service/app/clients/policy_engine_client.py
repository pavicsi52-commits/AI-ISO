"""Live policy evaluation against the Policy Engine Service, backing
this service's ``POLICY_ENFORCEMENT`` guardrail (docs/060 "GUARDRAILS").

Policy-engine-service's own guardrail vocabulary (``app/guardrails
/builtin.py``'s ``BUILTIN_GUARDRAILS``, full ABAC ``Rule``/
``Condition``/``PolicyEffect``) is genuinely richer than the regex-
based checks this service mirrors from ``ai-assistant-service`` for
Prompt/Output Validation, PII, and Secret Redaction -- so rather than
reimplementing ABAC policy evaluation a second time, Policy Enforcement
calls the real thing live, the same "a small number of established
exceptions make genuine live HTTP calls to a sibling service" pattern
:class:`~app.clients.automation_client.AutomationClient` already uses.

Mirrors ``AutomationClient``'s own shape: an ``httpx.AsyncClient``
passed in, a per-call ``caller_token`` constructed fresh from whoever
initiated the owning execution, and a :class:`~shared_core.exceptions
.dependency.DependencyError` on anything short of a clean answer.

Every field this client sends is a **plain string**, never
``policy-engine-service``'s own ``SubjectType``/``ResourceType``/
``ActionType`` enums -- importing those would violate this platform's
zero-cross-service-import convention; the wire values are simply
strings that happen to match that service's own documented vocabulary,
which the caller of this client is responsible for supplying correctly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """One authorization answer from the Policy Engine Service."""

    effect: str
    permitted: bool
    denied: bool
    reason: str
    risk_score: float = 0.0
    obligations: dict[str, Any] = field(default_factory=dict)
    decision_id: str | None = None

    @property
    def requires_approval(self) -> bool:
        """Whether this decision raised a pending approval obligation
        rather than a plain allow or deny."""
        return self.effect == "require_approval"


class PolicyEngineClient:
    """Asks the Policy Engine Service whether one operation is permitted."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        caller_token: str,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._caller_token = caller_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._caller_token}"}

    async def evaluate(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: str,
        resource_type: str,
        action: str,
        resource_id: str | None = None,
        project_id: str | None = None,
        attributes: dict[str, dict[str, Any]] | None = None,
        record: bool = True,
    ) -> PolicyDecision:
        """Ask whether one operation is permitted.

        *attributes* is a mapping of ABAC attribute categories
        (``subject``/``resource``/``action``/``context``/
        ``environment``/``organization``/``project``/``custom``) to
        their own key/value pairs, matching the Policy Engine Service's
        own ``EvaluationContextPayload`` shape.

        Raises:
            DependencyError: If the Policy Engine Service is
                unreachable or returns anything other than ``200``.
        """
        payload: dict[str, Any] = {
            "subject_type": subject_type,
            "subject_id": subject_id,
            "resource_type": resource_type,
            "action": action,
            "resource_id": resource_id,
            "project_id": project_id,
            "attributes": attributes or {},
            "record": record,
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/policies/evaluate",
                params={"organization_id": str(organization_id)},
                json=payload,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Policy Engine Service unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"Policy Engine Service returned HTTP {response.status_code} "
                f"evaluating {action!r} on {resource_type!r}."
            )

        decision = response.json()["data"]
        return PolicyDecision(
            effect=decision["effect"],
            permitted=decision["permitted"],
            denied=decision["denied"],
            reason=decision["reason"],
            risk_score=decision.get("risk_score", 0.0),
            obligations=decision.get("obligations") or {},
            decision_id=decision.get("decision_id"),
        )


__all__ = ["PolicyDecision", "PolicyEngineClient"]
