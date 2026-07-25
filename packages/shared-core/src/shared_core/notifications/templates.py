"""Template registry.

Per docs/025_Enterprise_Notification_Framework.md.txt "TEMPLATE ENGINE":
HTML, Markdown, Plain Text, Subject Templates, Variable Replacement,
Localization, Versioning, Preview, Validation. This module owns
*registration and lookup*; :mod:`shared_core.notifications.renderer`
owns actually rendering one against a variable set.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_core.notifications.exceptions import TemplateNotFoundError


class TemplateFormat(StrEnum):
    """Every body format docs/025 "TEMPLATE ENGINE" names."""

    HTML = "html"
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"


@dataclass(frozen=True, slots=True)
class Template:
    """One registered, versioned, localized notification template."""

    template_id: str
    body_template: str
    format: TemplateFormat
    version: int = 1
    locale: str = "en"
    subject_template: str | None = None


class TemplateRegistry:
    """Registry of templates, keyed by ``(template_id, locale, version)``.

    Registering the same ``template_id``/``locale`` again with a higher
    ``version`` keeps the old version retrievable by explicit version
    number ("Versioning") while :meth:`get` without one returns the
    latest.
    """

    def __init__(self) -> None:
        self._templates: dict[tuple[str, str, int], Template] = {}
        self._latest_version: dict[tuple[str, str], int] = {}

    def register(self, template: Template) -> None:
        """Register *template*, becoming the latest version for its ``(id, locale)``."""
        key = (template.template_id, template.locale, template.version)
        self._templates[key] = template
        latest_key = (template.template_id, template.locale)
        current_latest = self._latest_version.get(latest_key, 0)
        if template.version >= current_latest:
            self._latest_version[latest_key] = template.version

    def get(self, template_id: str, *, locale: str = "en", version: int | None = None) -> Template:
        """Return the registered template, falling back from *locale* to ``"en"``.

        Raises:
            TemplateNotFoundError: If no matching template is registered
                in either *locale* or the ``"en"`` fallback.
        """
        resolved_version = version or self._latest_version.get((template_id, locale))
        if resolved_version is not None:
            template = self._templates.get((template_id, locale, resolved_version))
            if template is not None:
                return template

        if locale != "en":
            fallback_version = version or self._latest_version.get((template_id, "en"))
            if fallback_version is not None:
                template = self._templates.get((template_id, "en", fallback_version))
                if template is not None:
                    return template

        raise TemplateNotFoundError(
            f"No template registered for id={template_id!r}, locale={locale!r}."
        )

    def list_ids(self) -> list[str]:
        """Every distinct registered template ID."""
        return sorted({template_id for template_id, _locale, _version in self._templates})


__all__ = ["Template", "TemplateFormat", "TemplateRegistry"]
