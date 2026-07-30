"""HTTP routers for the policy engine service.

**Include order matters.** Both routers are mounted under ``/policies``,
and ``operations_router`` owns literal segments -- ``/policies/decisions``,
``/policies/quotas``, ``/policies/audit`` -- while ``policies_router`` owns
``/policies/{policy_id}``. FastAPI matches in registration order, so the
literal-segment router must be included first or ``/policies/decisions``
would be parsed as a policy whose id is the word "decisions" and answer
422 for a malformed UUID.
"""

from __future__ import annotations

from app.api.health import router as health_router
from app.api.operations import router as operations_router
from app.api.policies import router as policies_router

__all__ = ["health_router", "operations_router", "policies_router"]
