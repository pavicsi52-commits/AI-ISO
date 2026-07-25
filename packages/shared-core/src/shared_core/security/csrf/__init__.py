"""CSRF protection: double-submit-cookie token generation/validation.

Per docs/017_Enterprise_Security_Framework.md.txt "CSRF": "Enable where
applicable. Token Validation." (Origin-header validation is
:func:`shared_core.validation.rules.security.validate_origin`'s job --
not duplicated here; that package already depends on this one, so the
reverse import would cycle.) The double-submit-cookie pattern needs no
server-side token storage: a token is set as a cookie *and* echoed by the
client in a header/form field, and a request is legitimate only if both
match -- an attacker forging a cross-site request can't read the cookie
to also set the header.
"""

from __future__ import annotations

import secrets

_CSRF_TOKEN_LENGTH_BYTES = 32


def generate_csrf_token() -> str:
    """Generate a new CSRF token."""
    return secrets.token_urlsafe(_CSRF_TOKEN_LENGTH_BYTES)


def validate_double_submit_token(*, cookie_token: str | None, header_token: str | None) -> bool:
    """Validate the double-submit-cookie pattern.

    The token in the cookie must match the token the client also sent in
    a header or form field, compared in constant time.
    """
    if not cookie_token or not header_token:
        return False
    return secrets.compare_digest(cookie_token, header_token)
