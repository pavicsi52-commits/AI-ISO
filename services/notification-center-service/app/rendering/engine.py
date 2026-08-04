"""Template rendering -- a thin adapter onto `shared_core.notifications.renderer`.

Per this prompt's own "use every previously implemented platform
framework" instruction: every actual rendering rule (Jinja2 sandboxing,
Markdown-to-HTML conversion, syntax validation) already lives in
`shared_core.notifications.renderer`/`.templates`; this module only
adapts this service's own stored template rows into the
`shared_core.notifications.templates.Template` shape that renderer
already knows how to render, and re-exports its functions so callers
never import `shared_core.notifications` directly.
"""

from __future__ import annotations

from typing import Any

from shared_core.notifications.renderer import RenderedNotification
from shared_core.notifications.renderer import preview_template as _preview_template
from shared_core.notifications.renderer import render_template as _render_template
from shared_core.notifications.renderer import render_to_html as _render_to_html
from shared_core.notifications.renderer import validate_template as _validate_template
from shared_core.notifications.templates import Template as SharedTemplate

from app.models.enums import TemplateFormat, to_shared_template_format


def to_shared_template(
    *,
    template_key: str,
    body_template: str,
    template_format: TemplateFormat,
    version: int = 1,
    locale: str = "en",
    subject_template: str | None = None,
) -> SharedTemplate:
    """Build the `shared_core` :class:`~shared_core.notifications.templates.Template`
    this service's own stored template (or one of its versions) renders through."""
    return SharedTemplate(
        template_id=template_key,
        body_template=body_template,
        format=to_shared_template_format(template_format),
        version=version,
        locale=locale,
        subject_template=subject_template,
    )


def render(template: SharedTemplate, variables: dict[str, Any]) -> RenderedNotification:
    """Render *template* against *variables*.

    Raises:
        shared_core.notifications.exceptions.TemplateRenderError: On
            invalid syntax, a missing variable, or a sandbox violation.
    """
    return _render_template(template, variables)


def render_to_html(rendered: RenderedNotification) -> str:
    """Render *rendered* to HTML, converting Markdown or escaping plain text as needed."""
    return _render_to_html(rendered)


def preview(template: SharedTemplate, sample_variables: dict[str, Any]) -> RenderedNotification:
    """Render *template* against *sample_variables* for a non-delivery preview."""
    return _preview_template(template, sample_variables)


def validate(template: SharedTemplate) -> None:
    """Check *template*'s Jinja2 syntax without rendering it.

    Raises:
        shared_core.notifications.exceptions.TemplateRenderError: If invalid.
    """
    _validate_template(template)


__all__ = ["render", "render_to_html", "preview", "to_shared_template", "validate"]
