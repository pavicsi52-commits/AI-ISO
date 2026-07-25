"""Tests for templates.py and renderer.py."""

from __future__ import annotations

import pytest
from shared_core.notifications.exceptions import TemplateNotFoundError, TemplateRenderError
from shared_core.notifications.renderer import (
    preview_template,
    render_template,
    render_to_html,
    validate_template,
)
from shared_core.notifications.templates import Template, TemplateFormat, TemplateRegistry

# --- templates.py ---


def test_template_registry_register_and_get_roundtrips() -> None:
    registry = TemplateRegistry()
    template = Template(
        template_id="welcome", body_template="Hi {{ name }}", format=TemplateFormat.PLAIN_TEXT
    )

    registry.register(template)

    assert registry.get("welcome") is template


def test_template_registry_get_raises_for_an_unregistered_template() -> None:
    with pytest.raises(TemplateNotFoundError):
        TemplateRegistry().get("nope")


def test_template_registry_get_falls_back_from_locale_to_english() -> None:
    registry = TemplateRegistry()
    english = Template(template_id="welcome", body_template="Hi", format=TemplateFormat.PLAIN_TEXT)
    registry.register(english)

    assert registry.get("welcome", locale="fr") is english


def test_template_registry_get_returns_the_latest_version_by_default() -> None:
    registry = TemplateRegistry()
    v1 = Template(
        template_id="welcome", body_template="v1", format=TemplateFormat.PLAIN_TEXT, version=1
    )
    v2 = Template(
        template_id="welcome", body_template="v2", format=TemplateFormat.PLAIN_TEXT, version=2
    )
    registry.register(v1)
    registry.register(v2)

    assert registry.get("welcome").body_template == "v2"
    assert registry.get("welcome", version=1).body_template == "v1"


def test_template_registry_list_ids_returns_every_distinct_id() -> None:
    registry = TemplateRegistry()
    registry.register(
        Template(template_id="a", body_template="x", format=TemplateFormat.PLAIN_TEXT)
    )
    registry.register(
        Template(template_id="b", body_template="y", format=TemplateFormat.PLAIN_TEXT)
    )

    assert registry.list_ids() == ["a", "b"]


# --- renderer.py ---


def test_render_template_substitutes_variables_in_body_and_subject() -> None:
    template = Template(
        template_id="welcome",
        body_template="Hi {{ name }}, welcome to {{ product }}.",
        subject_template="Welcome, {{ name }}!",
        format=TemplateFormat.PLAIN_TEXT,
    )

    rendered = render_template(template, {"name": "Ada", "product": "AI-IOS"})

    assert rendered.body == "Hi Ada, welcome to AI-IOS."
    assert rendered.subject == "Welcome, Ada!"


def test_render_template_renders_a_missing_attribute_as_empty_rather_than_raising() -> None:
    template = Template(
        template_id="welcome",
        body_template="Hi {{ name.missing_attr }}",
        format=TemplateFormat.PLAIN_TEXT,
    )

    rendered = render_template(template, {"name": object()})

    assert rendered.body == "Hi "


def test_render_template_raises_on_invalid_syntax() -> None:
    template = Template(
        template_id="broken", body_template="Hi {{ name", format=TemplateFormat.PLAIN_TEXT
    )

    with pytest.raises(TemplateRenderError):
        render_template(template, {"name": "Ada"})


def test_render_template_cannot_reach_python_internals() -> None:
    template = Template(
        template_id="malicious",
        body_template="{{ ''.__class__.__mro__[1].__subclasses__() }}",
        format=TemplateFormat.PLAIN_TEXT,
    )

    with pytest.raises(TemplateRenderError):
        render_template(template, {})


def test_render_to_html_passes_html_through_unchanged() -> None:
    rendered = render_template(
        Template(template_id="t", body_template="<b>hi</b>", format=TemplateFormat.HTML), {}
    )

    assert render_to_html(rendered) == "<b>hi</b>"


def test_render_to_html_converts_markdown() -> None:
    rendered = render_template(
        Template(template_id="t", body_template="# Hello", format=TemplateFormat.MARKDOWN), {}
    )

    assert render_to_html(rendered) == "<h1>Hello</h1>"


def test_render_to_html_escapes_plain_text() -> None:
    rendered = render_template(
        Template(template_id="t", body_template="a < b & c", format=TemplateFormat.PLAIN_TEXT), {}
    )

    assert render_to_html(rendered) == "<pre>a &lt; b &amp; c</pre>"


def test_preview_template_is_equivalent_to_render_template() -> None:
    template = Template(
        template_id="t", body_template="Hi {{ name }}", format=TemplateFormat.PLAIN_TEXT
    )

    assert preview_template(template, {"name": "Ada"}).body == "Hi Ada"


def test_validate_template_passes_for_valid_syntax() -> None:
    template = Template(
        template_id="t", body_template="Hi {{ name }}", format=TemplateFormat.PLAIN_TEXT
    )

    validate_template(template)


def test_validate_template_raises_for_invalid_syntax() -> None:
    template = Template(
        template_id="t", body_template="Hi {{ name", format=TemplateFormat.PLAIN_TEXT
    )

    with pytest.raises(TemplateRenderError):
        validate_template(template)


def test_validate_template_checks_the_subject_template_too() -> None:
    template = Template(
        template_id="t",
        body_template="ok",
        subject_template="Hi {{ name",
        format=TemplateFormat.PLAIN_TEXT,
    )

    with pytest.raises(TemplateRenderError):
        validate_template(template)
