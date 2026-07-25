"""Localization middleware.

Resolves the caller's preferred locale from ``Accept-Language`` and stores
it on request state. Message translation itself lives in
:mod:`shared_core.exceptions.constants` (``MESSAGE_CATALOG``,
``localize_message``) per docs/015_Enterprise_Exception_Framework.md.txt
"LOCALIZATION" — this middleware only resolves *which* locale to translate
into.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = frozenset({"en", "es"})


def parse_preferred_locale(accept_language: str | None) -> str:
    """Parse the ``Accept-Language`` header and return a supported locale.

    Falls back to :data:`DEFAULT_LOCALE` if the header is absent or no
    requested locale is supported.
    """
    if not accept_language:
        return DEFAULT_LOCALE

    for entry in accept_language.split(","):
        locale = entry.split(";")[0].strip().split("-")[0].lower()
        if locale in SUPPORTED_LOCALES:
            return locale

    return DEFAULT_LOCALE


class LocalizationMiddleware:
    """ASGI middleware resolving the caller's preferred locale onto request state."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        locale = parse_preferred_locale(request.headers.get("accept-language"))

        scope["state"] = scope.get("state", {})
        scope["state"]["locale"] = locale

        await self._app(scope, receive, send)
