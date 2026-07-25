"""Tests for configurable security headers, CORS, and CSRF."""

from __future__ import annotations

from shared_core.security.cors import (
    CorsConfig,
    development_cors_config,
    is_origin_allowed,
    production_cors_config,
)
from shared_core.security.csrf import generate_csrf_token, validate_double_submit_token
from shared_core.security.headers import (
    SecurityHeadersConfig,
    build_security_headers,
    development_headers,
    production_headers,
)

# --- headers/ ---


def test_build_security_headers_uses_defaults() -> None:
    headers = build_security_headers()

    assert headers["X-Frame-Options"] == "DENY"
    assert "max-age=63072000" in headers["Strict-Transport-Security"]


def test_build_security_headers_respects_custom_config() -> None:
    config = SecurityHeadersConfig(x_frame_options="SAMEORIGIN")

    headers = build_security_headers(config)

    assert headers["X-Frame-Options"] == "SAMEORIGIN"


def test_development_headers_disable_hsts() -> None:
    headers = development_headers()

    assert headers["Strict-Transport-Security"] == "max-age=0"


def test_development_headers_permit_inline_scripts() -> None:
    headers = development_headers()

    assert "unsafe-inline" in headers["Content-Security-Policy"]


def test_production_headers_are_strict() -> None:
    headers = production_headers()

    assert "unsafe-inline" not in headers["Content-Security-Policy"]
    assert "includeSubDomains" in headers["Strict-Transport-Security"]


# --- cors/ ---


def test_development_cors_config_allows_any_origin() -> None:
    config = development_cors_config()

    assert is_origin_allowed("https://anything.example", config=config) is True


def test_production_cors_config_only_allows_listed_origins() -> None:
    config = production_cors_config(["https://app.aiios.example"])

    assert is_origin_allowed("https://app.aiios.example", config=config) is True
    assert is_origin_allowed("https://evil.example", config=config) is False


def test_production_cors_config_allows_credentials() -> None:
    config = production_cors_config(["https://app.aiios.example"])

    assert config.allow_credentials is True


def test_cors_config_default_methods() -> None:
    config = CorsConfig()

    assert "GET" in config.allow_methods
    assert "DELETE" in config.allow_methods


# --- csrf/ ---


def test_generate_csrf_token_is_unique_each_time() -> None:
    assert generate_csrf_token() != generate_csrf_token()


def test_validate_double_submit_token_passes_for_matching_tokens() -> None:
    token = generate_csrf_token()

    result = validate_double_submit_token(cookie_token=token, header_token=token)

    assert result is True


def test_validate_double_submit_token_fails_for_mismatched_tokens() -> None:
    result = validate_double_submit_token(
        cookie_token=generate_csrf_token(), header_token=generate_csrf_token()
    )

    assert result is False


def test_validate_double_submit_token_fails_when_cookie_missing() -> None:
    result = validate_double_submit_token(cookie_token=None, header_token="some-token")

    assert result is False


def test_validate_double_submit_token_fails_when_header_missing() -> None:
    result = validate_double_submit_token(cookie_token="some-token", header_token=None)

    assert result is False
