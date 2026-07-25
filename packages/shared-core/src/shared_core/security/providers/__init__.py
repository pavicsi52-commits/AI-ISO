"""Pluggable authentication provider interfaces.

Per docs/017_Enterprise_Security_Framework.md.txt "AUTHENTICATION":
"Future: OAuth2, OIDC, SAML, LDAP, Active Directory" and "Future SSO" --
these are structural interfaces only. No concrete provider is implemented
(docs/017 "DO NOT IMPLEMENT": "Authentication Service").
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AuthenticationProvider(Protocol):
    """Structural interface every external authentication provider
    (OAuth2, OIDC, SAML, LDAP, Active Directory, SSO) implements.
    """

    provider_name: str

    async def authenticate(self, credentials: dict[str, Any]) -> dict[str, Any]:
        """Authenticate against the external provider, returning claims."""
        ...
