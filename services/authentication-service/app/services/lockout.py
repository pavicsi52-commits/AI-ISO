"""Account lockout and failed-login tracking.

Per docs/030 "ACCOUNT SECURITY": Failed Login Tracking, Progressive
Delay, Temporary Lockout, Permanent Lockout, CAPTCHA Hook, Suspicious
Activity Detection. "CAPTCHA Hook" and "Suspicious Activity Detection"
are exposed as caller-checkable signals (:meth:`LockoutService
.captcha_required`) rather than implemented -- this service has no
CAPTCHA provider or anomaly-detection model of its own, matching
docs/030's own "framework hooks" framing for "Risk Detection" under
"LOGIN".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import FailedLoginReason
from app.models.failed_login import FailedLoginEntry
from app.models.user import User
from app.repositories.failed_login import FailedLoginRepository

_TRACKING_WINDOW_MINUTES = 15
_CAPTCHA_THRESHOLD = 3
_TEMPORARY_LOCKOUT_THRESHOLD = 5
_TEMPORARY_LOCKOUT_MINUTES = 15
_PERMANENT_LOCKOUT_THRESHOLD = 10
_PERMANENT_LOCKOUT_DAYS = 365
_PROGRESSIVE_DELAY_BASE_SECONDS = 2.0
_PROGRESSIVE_DELAY_MAX_SECONDS = 30.0


class LockoutService:
    """Tracks failed logins and computes progressive delay/lockout."""

    def __init__(self, failed_logins: FailedLoginRepository) -> None:
        self._failed_logins = failed_logins

    async def record_failure(
        self,
        identifier: str,
        *,
        reason: FailedLoginReason,
        user_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Record one failed attempt against *identifier* ("Failed Login Tracking")."""
        await self._failed_logins.create(
            FailedLoginEntry(
                user_id=user_id,
                identifier=identifier,
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    async def recent_failure_count(self, identifier: str) -> int:
        """How many times *identifier* has failed within the tracking window."""
        since = datetime.now(UTC) - timedelta(minutes=_TRACKING_WINDOW_MINUTES)
        return await self._failed_logins.count_recent_for_identifier(identifier, since=since)

    async def captcha_required(self, identifier: str) -> bool:
        """Whether *identifier* has failed enough recently to require a CAPTCHA ("CAPTCHA Hook")."""
        return await self.recent_failure_count(identifier) >= _CAPTCHA_THRESHOLD

    async def compute_delay_seconds(self, identifier: str) -> float:
        """The client-side retry delay *identifier* should observe ("Progressive Delay").

        Doubles per recent failure, capped -- returned to the client as
        a ``retry_after_seconds`` hint rather than held open server-side.
        """
        count = await self.recent_failure_count(identifier)
        if count == 0:
            return 0.0
        return min(_PROGRESSIVE_DELAY_BASE_SECONDS**count, _PROGRESSIVE_DELAY_MAX_SECONDS)

    async def compute_lockout_until(self, identifier: str) -> datetime | None:
        """How long *identifier* should be locked out, or ``None`` if not yet warranted.

        Crossing the temporary threshold locks briefly ("Temporary
        Lockout"); crossing the permanent threshold locks for a full
        year, effectively requiring operator intervention ("Permanent
        Lockout").
        """
        count = await self.recent_failure_count(identifier)
        now = datetime.now(UTC)
        if count >= _PERMANENT_LOCKOUT_THRESHOLD:
            return now + timedelta(days=_PERMANENT_LOCKOUT_DAYS)
        if count >= _TEMPORARY_LOCKOUT_THRESHOLD:
            return now + timedelta(minutes=_TEMPORARY_LOCKOUT_MINUTES)
        return None

    def is_locked(self, user: User) -> bool:
        """Whether *user* is currently locked out."""
        return user.locked_until is not None and user.locked_until > datetime.now(UTC)


__all__ = ["LockoutService"]
