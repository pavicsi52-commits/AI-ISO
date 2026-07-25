"""MFA (TOTP) enrollment and verification.

Per docs/030 "MULTI-FACTOR AUTHENTICATION": TOTP, Recovery Codes,
Backup Codes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote
from uuid import UUID

from shared_core.exceptions.authentication import AuthenticationError
from shared_core.helpers.hash_helper import sha256_hex
from shared_core.security.mfa import (
    generate_recovery_codes,
    generate_totp_secret,
    verify_recovery_code,
    verify_totp_code,
)

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import MfaDeviceType
from app.models.mfa import MfaDevice
from app.repositories.mfa import MfaDeviceRepository

_OTPAUTH_ISSUER = "AI-IOS"


class MfaService:
    """Enrolls, verifies, and disables TOTP-based MFA."""

    def __init__(self, devices: MfaDeviceRepository) -> None:
        self._devices = devices

    async def enable(self, user_id: UUID) -> tuple[MfaDevice, list[str]]:
        """Enroll a new, not-yet-verified TOTP device, returning it plus plaintext recovery codes.

        The device isn't enforced at login until the caller confirms
        possession via :meth:`verify_enrollment`.
        """
        secret = generate_totp_secret()
        raw_codes = generate_recovery_codes()
        device = await self._devices.create(
            MfaDevice(
                user_id=user_id,
                device_type=MfaDeviceType.TOTP,
                secret=secret,
                recovery_codes_hashed=[sha256_hex(code) for code in raw_codes],
                is_primary=True,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        return device, raw_codes

    def build_otpauth_uri(self, secret: str, *, email: str) -> str:
        """The ``otpauth://`` URI an authenticator app scans to enroll *secret*."""
        label = quote(f"{_OTPAUTH_ISSUER}:{email}")
        return f"otpauth://totp/{label}?secret={secret}&issuer={quote(_OTPAUTH_ISSUER)}"

    def verify_enrollment(self, device: MfaDevice, code: str) -> None:
        """Confirm *device*'s owner actually possesses the secret before enforcing it.

        Raises:
            AuthenticationError: If *code* doesn't verify.
        """
        if not verify_totp_code(device.secret, code):
            raise AuthenticationError("Invalid MFA code.")
        device.is_verified = True

    async def confirm_enrollment(self, user_id: UUID, code: str) -> MfaDevice:
        """Confirm *user_id*'s pending (just-enrolled) device using its verification code.

        Raises:
            AuthenticationError: If no device is pending, or *code* doesn't verify.
        """
        device = await self._devices.get_primary_for_user(user_id)
        if device is None:
            raise AuthenticationError("No MFA device is pending verification.")
        self.verify_enrollment(device, code)
        return device

    async def has_verified_device(self, user_id: UUID) -> bool:
        """Whether *user_id* has a verified (login-enforced) MFA device."""
        device = await self._devices.get_primary_for_user(user_id)
        return device is not None and device.is_verified

    async def verify(self, user_id: UUID, code: str) -> bool:
        """Verify *code* against *user_id*'s primary device (a TOTP code or a recovery code)."""
        device = await self._devices.get_primary_for_user(user_id)
        if device is None or not device.is_verified:
            return False
        if verify_totp_code(device.secret, code):
            device.last_used_at = datetime.now(UTC)
            return True
        hashed_code = sha256_hex(code)
        codes = device.recovery_codes_hashed or []
        if verify_recovery_code(hashed_code, valid_codes=codes):
            device.recovery_codes_hashed = [c for c in codes if c != hashed_code]
            device.last_used_at = datetime.now(UTC)
            return True
        return False

    async def disable(self, user_id: UUID) -> None:
        """Remove every MFA device registered to *user_id*."""
        for device in await self._devices.list_for_user(user_id):
            await self._devices.delete(device.id)


__all__ = ["MfaService"]
