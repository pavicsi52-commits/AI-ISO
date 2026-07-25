"""Template rendering.

Per docs/025_Enterprise_Notification_Framework.md.txt "TEMPLATE ENGINE":
Variable Replacement, Preview, Validation, plus converting a Markdown
body to HTML for channels that want it. Uses Jinja2's
:class:`~jinja2.sandbox.SandboxedEnvironment` -- a notification template
may ultimately come from a service's own (possibly user-editable)
configuration, not just trusted source code, so unrestricted Jinja2
(capable of reaching arbitrary Python attributes) would be a real
injection risk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import markdown as markdown_lib
from jinja2 import TemplateError, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment

from shared_core.notifications.exceptions import TemplateRenderError
from shared_core.notifications.templates import Template, TemplateFormat

_env = SandboxedEnvironment(autoescape=False)


@dataclass(frozen=True, slots=True)
class RenderedNotification:
    """The result of rendering a :class:`Template` against a variable set."""

    body: str
    format: TemplateFormat
    subject: str | None = None


def render_template(template: Template, variables: dict[str, Any]) -> RenderedNotification:
    """Render *template*'s subject and body against *variables* ("Variable Replacement").

    Raises:
        TemplateRenderError: If either template has invalid Jinja2
            syntax, a referenced variable is missing, or the template
            attempts to reach outside the sandbox.
    """
    try:
        body = _env.from_string(template.body_template).render(**variables)
        subject = (
            _env.from_string(template.subject_template).render(**variables)
            if template.subject_template is not None
            else None
        )
    except TemplateError as exc:
        raise TemplateRenderError(
            f"Failed to render template {template.template_id!r}: {exc}"
        ) from exc
    return RenderedNotification(body=body, format=template.format, subject=subject)


def render_to_html(rendered: RenderedNotification) -> str:
    """Render *rendered* to HTML, converting Markdown if needed.

    Plain text is escaped-and-wrapped minimally (a ``<pre>`` block) so
    it renders legibly in an HTML-only channel (e.g. an email client)
    without being reinterpreted as HTML markup.
    """
    if rendered.format == TemplateFormat.HTML:
        return rendered.body
    if rendered.format == TemplateFormat.MARKDOWN:
        return markdown_lib.markdown(rendered.body)
    escaped = rendered.body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<pre>{escaped}</pre>"


def preview_template(template: Template, sample_variables: dict[str, Any]) -> RenderedNotification:
    """Render *template* against *sample_variables* for a non-delivery preview ("Preview")."""
    return render_template(template, sample_variables)


def validate_template(template: Template) -> None:
    """Check *template*'s Jinja2 syntax without rendering it ("Validation").

    Raises:
        TemplateRenderError: If either the subject or body template has
            invalid syntax.
    """
    try:
        _env.parse(template.body_template)
        if template.subject_template is not None:
            _env.parse(template.subject_template)
    except TemplateSyntaxError as exc:
        raise TemplateRenderError(
            f"Template {template.template_id!r} has invalid syntax: {exc}"
        ) from exc


__all__ = [
    "RenderedNotification",
    "preview_template",
    "render_template",
    "render_to_html",
    "validate_template",
]
