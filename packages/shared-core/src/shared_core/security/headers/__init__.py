"""Configurable security response headers.

Per docs/017_Enterprise_Security_Framework.md.txt "SECURITY HEADERS":
HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy,
Permissions-Policy, X-XSS-Protection -- "Environment Specific" (a
permissive CSP for local development, strict everywhere else). Expands
:mod:`shared_core.middleware.security_headers`'s fixed Prompt 012 header
set into a configurable one; that middleware's defaults are unchanged, so
services that haven't opted into the new configurability keep working
identically.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SecurityHeadersConfig:
    """Configurable values for every header docs/017 "SECURITY HEADERS" lists."""

    hsts_max_age_seconds: int = 63_072_000
    hsts_include_subdomains: bool = True
    content_security_policy: str = "default-src 'self'"
    x_frame_options: str = "DENY"
    x_content_type_options: str = "nosniff"
    referrer_policy: str = "strict-origin-when-cross-origin"
    permissions_policy: str = "geolocation=(), camera=(), microphone=()"
    x_xss_protection: str = "0"


def build_security_headers(config: SecurityHeadersConfig | None = None) -> dict[str, str]:
    """Build the security response header set from *config* (or strict defaults)."""
    cfg = config or SecurityHeadersConfig()
    hsts_value = f"max-age={cfg.hsts_max_age_seconds}"
    if cfg.hsts_include_subdomains:
        hsts_value += "; includeSubDomains"
    return {
        "Strict-Transport-Security": hsts_value,
        "Content-Security-Policy": cfg.content_security_policy,
        "X-Frame-Options": cfg.x_frame_options,
        "X-Content-Type-Options": cfg.x_content_type_options,
        "Referrer-Policy": cfg.referrer_policy,
        "Permissions-Policy": cfg.permissions_policy,
        "X-XSS-Protection": cfg.x_xss_protection,
    }


def development_headers() -> dict[str, str]:
    """A relaxed header set for local development: no HSTS, permissive CSP."""
    return build_security_headers(
        SecurityHeadersConfig(
            hsts_max_age_seconds=0,
            hsts_include_subdomains=False,
            content_security_policy="default-src 'self' 'unsafe-inline' 'unsafe-eval'",
        )
    )


def production_headers() -> dict[str, str]:
    """The strict default header set for production."""
    return build_security_headers()
