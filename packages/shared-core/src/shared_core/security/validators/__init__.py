"""Security-specific validation helpers.

Per docs/017_Enterprise_Security_Framework.md.txt "SECURITY VALIDATION":
Passwords, Tokens, Secrets, Certificates, Permissions, API Keys,
Sessions, Headers. Password/token/secret/permission/API-key/session
validation already live in their respective subpackages (``password/``,
``jwt/``, ``secrets/``, ``rbac/``, ``apikey/``, ``sessions/``); this
module covers certificates and headers, which have no other home.

Deliberately does not import :mod:`shared_core.validation` -- that
package already depends on :mod:`shared_core.security` (Prompt 016), so
the reverse import would cycle.
"""

from __future__ import annotations

from shared_core.security.certificates import is_certificate_expired, parse_certificate


def validate_certificate_pem(pem_data: str) -> bool:
    """Return whether *pem_data* parses as a well-formed X.509 certificate."""
    try:
        parse_certificate(pem_data)
    except ValueError:
        return False
    return True


def validate_certificate_not_expired(pem_data: str) -> bool:
    """Return whether *pem_data* parses as a certificate and hasn't expired."""
    try:
        certificate = parse_certificate(pem_data)
    except ValueError:
        return False
    return not is_certificate_expired(certificate)


def validate_required_security_headers(
    headers: dict[str, str], *, required: tuple[str, ...]
) -> bool:
    """Return whether every header in *required* is present (case-insensitive)."""
    present = {name.lower() for name in headers}
    return all(name.lower() in present for name in required)
