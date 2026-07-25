"""Multi-factor authentication: TOTP, email OTP, recovery codes, trusted devices.

Per docs/017_Enterprise_Security_Framework.md.txt "MULTI FACTOR
AUTHENTICATION". TOTP implements RFC 6238 directly against the standard
library (``hmac``/``hashlib``/``struct``) -- no new dependency. WebAuthn
and FIDO2 are explicitly future work.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from collections.abc import Collection

from shared_core.security.constants import SecurityFrameworkConstants

_TOTP_WINDOW = 1  # tolerate +/- 1 period of clock drift


def generate_totp_secret() -> str:
    """Generate a new base32-encoded TOTP secret."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def generate_totp_code(secret: str, *, timestamp: float | None = None) -> str:
    """Generate the current TOTP code for *secret* (RFC 6238)."""
    counter = int((timestamp or time.time()) // SecurityFrameworkConstants.TOTP_PERIOD_SECONDS)
    return _hotp(secret, counter)


def verify_totp_code(secret: str, code: str, *, timestamp: float | None = None) -> bool:
    """Verify *code* against *secret*, tolerating a small window of clock drift."""
    current_counter = int(
        (timestamp or time.time()) // SecurityFrameworkConstants.TOTP_PERIOD_SECONDS
    )
    return any(
        hmac.compare_digest(_hotp(secret, current_counter + offset), code)
        for offset in range(-_TOTP_WINDOW, _TOTP_WINDOW + 1)
    )


def _hotp(secret: str, counter: int) -> str:
    # RFC 6238 (TOTP) mandates HMAC-SHA1 for interoperability with
    # standard authenticator apps (Google Authenticator, Authy, ...);
    # this is the deployed standard, not a weakened choice.
    key = base64.b32decode(secret.upper())
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**SecurityFrameworkConstants.TOTP_DIGITS)).zfill(
        SecurityFrameworkConstants.TOTP_DIGITS
    )


def generate_email_otp() -> str:
    """Generate a 6-digit numeric one-time code for email delivery."""
    return f"{secrets.randbelow(10**6):06d}"


def generate_recovery_codes(
    count: int = SecurityFrameworkConstants.RECOVERY_CODE_COUNT,
) -> list[str]:
    """Generate a batch of single-use MFA recovery codes."""
    return [secrets.token_hex(5) for _ in range(count)]


def verify_recovery_code(code: str, *, valid_codes: Collection[str]) -> bool:
    """Check *code* against the caller's remaining unused recovery codes."""
    return code in valid_codes


def generate_trusted_device_token() -> str:
    """Generate a token identifying a device that may skip MFA for a grace period."""
    return secrets.token_urlsafe(32)
