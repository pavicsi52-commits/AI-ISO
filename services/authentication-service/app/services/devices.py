"""Device tracking and trust management.

Per docs/030 "DEVICE MANAGEMENT": Device ID, Browser, Operating
System, IP Address, Location, Last Login, Trusted Status, Device
Revocation. Per "LOGIN": Trusted Device.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError
from shared_core.security.constants import SecurityFrameworkConstants

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.trusted_device import TrustedDevice
from app.repositories.device import TrustedDeviceRepository


class DeviceService:
    """Tracks devices a user has logged in from and manages trusted status."""

    def __init__(self, devices: TrustedDeviceRepository) -> None:
        self._devices = devices

    async def record_login(
        self,
        user_id: UUID,
        *,
        device_fingerprint: str,
        device_name: str | None = None,
        browser: str | None = None,
        operating_system: str | None = None,
        ip_address: str | None = None,
        location: str | None = None,
    ) -> TrustedDevice:
        """Record (or update) a device's last-login info, creating it if new."""
        device = await self._devices.get_by_fingerprint(user_id, device_fingerprint)
        now = datetime.now(UTC)
        if device is None:
            return await self._devices.create(
                TrustedDevice(
                    user_id=user_id,
                    device_fingerprint=device_fingerprint,
                    device_name=device_name,
                    browser=browser,
                    operating_system=operating_system,
                    ip_address=ip_address,
                    location=location,
                    last_login_at=now,
                    organization_id=DEFAULT_ORGANIZATION_ID,
                )
            )
        device.last_login_at = now
        device.ip_address = ip_address or device.ip_address
        device.location = location or device.location
        return device

    def mark_trusted(self, device: TrustedDevice) -> None:
        """Mark *device* trusted for the standard grace period ("Trusted Devices")."""
        device.is_trusted = True
        device.trusted_until = datetime.now(UTC) + timedelta(
            days=SecurityFrameworkConstants.TRUSTED_DEVICE_TTL_DAYS
        )

    def is_currently_trusted(self, device: TrustedDevice) -> bool:
        """Whether *device* is trusted, not revoked, and within its trust window."""
        if not device.is_trusted or device.revoked_at is not None:
            return False
        return device.trusted_until is None or device.trusted_until > datetime.now(UTC)

    async def list_for_user(self, user_id: UUID) -> list[TrustedDevice]:
        """Every device on record for *user_id* ("GET /auth/devices")."""
        return await self._devices.list_for_user(user_id)

    async def revoke(self, user_id: UUID, device_id: UUID) -> None:
        """Revoke *user_id*'s device with id *device_id* ("Device Revocation").

        Raises:
            NotFoundError: If no such device belongs to *user_id*.
        """
        record = await self._devices.require_by_id(device_id)
        if record.user_id != user_id:
            raise NotFoundError(f"Device '{device_id}' was not found.")
        record.revoked_at = datetime.now(UTC)
        record.is_trusted = False


__all__ = ["DeviceService"]
