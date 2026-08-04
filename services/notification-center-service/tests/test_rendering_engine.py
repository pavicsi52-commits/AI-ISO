"""Pure tests for app/rendering/engine.py -- no database, no fixtures."""

from __future__ import annotations

import pytest
from shared_core.notifications.exceptions import TemplateRenderError
from shared_core.notifications.templates import TemplateFormat as SharedTemplateFormat

from app.models.enums import TemplateFormat
from app.rendering.engine import preview, render, render_to_html, to_shared_template, validate

pytestmark = pytest.mark.asyncio


class TestToSharedTemplate:
    async def test_maps_every_field_onto_the_shared_template(self) -> None:
        shared = to_shared_template(
            template_key="welcome_email",
            body_template="Hello {{ name }}",
            template_format=TemplateFormat.HTML,
            version=3,
            locale="fr",
            subject_template="Subject {{ name }}",
        )
        assert shared.template_id == "welcome_email"
        assert shared.body_template == "Hello {{ name }}"
        assert shared.version == 3
        assert shared.locale == "fr"
        assert shared.subject_template == "Subject {{ name }}"

    async def test_format_is_translated_through_to_shared_template_format(self) -> None:
        shared = to_shared_template(
            template_key="t1", body_template="body", template_format=TemplateFormat.MARKDOWN
        )
        assert shared.format == SharedTemplateFormat.MARKDOWN

    async def test_defaults_version_one_locale_en_and_no_subject(self) -> None:
        shared = to_shared_template(
            template_key="t1", body_template="body", template_format=TemplateFormat.PLAIN_TEXT
        )
        assert shared.version == 1
        assert shared.locale == "en"
        assert shared.subject_template is None


class TestRender:
    async def test_substitutes_jinja2_variables_in_the_body(self) -> None:
        template = to_shared_template(
            template_key="t1", body_template="Hello {{ name }}!", template_format=TemplateFormat.PLAIN_TEXT
        )
        rendered = render(template, {"name": "World"})
        assert rendered.body == "Hello World!"

    async def test_substitutes_jinja2_variables_in_the_subject(self) -> None:
        template = to_shared_template(
            template_key="t1",
            body_template="body",
            template_format=TemplateFormat.PLAIN_TEXT,
            subject_template="Subj {{ name }}",
        )
        rendered = render(template, {"name": "Ada"})
        assert rendered.subject == "Subj Ada"

    async def test_raises_template_render_error_on_bad_jinja2_syntax(self) -> None:
        template = to_shared_template(
            template_key="t1", body_template="{{ unclosed", template_format=TemplateFormat.PLAIN_TEXT
        )
        with pytest.raises(TemplateRenderError):
            render(template, {})


class TestPreview:
    async def test_renders_against_sample_variables_like_render_does(self) -> None:
        template = to_shared_template(
            template_key="t1", body_template="Hi {{ name }}", template_format=TemplateFormat.PLAIN_TEXT
        )
        rendered = preview(template, {"name": "Sample"})
        assert rendered.body == "Hi Sample"

    async def test_raises_template_render_error_on_bad_jinja2_syntax(self) -> None:
        template = to_shared_template(
            template_key="t1", body_template="{{ bad !! }}", template_format=TemplateFormat.PLAIN_TEXT
        )
        with pytest.raises(TemplateRenderError):
            preview(template, {})


class TestValidate:
    async def test_valid_syntax_does_not_raise(self) -> None:
        template = to_shared_template(
            template_key="t1", body_template="Hello {{ name }}", template_format=TemplateFormat.PLAIN_TEXT
        )
        validate(template)

    async def test_invalid_body_syntax_raises_template_render_error(self) -> None:
        template = to_shared_template(
            template_key="t1", body_template="{{ unclosed", template_format=TemplateFormat.PLAIN_TEXT
        )
        with pytest.raises(TemplateRenderError):
            validate(template)

    async def test_invalid_subject_syntax_raises_template_render_error(self) -> None:
        template = to_shared_template(
            template_key="t1",
            body_template="fine",
            template_format=TemplateFormat.PLAIN_TEXT,
            subject_template="{{ unclosed",
        )
        with pytest.raises(TemplateRenderError):
            validate(template)


class TestRenderToHtml:
    async def test_html_format_is_returned_unchanged(self) -> None:
        template = to_shared_template(
            template_key="t1", body_template="<b>{{ name }}</b>", template_format=TemplateFormat.HTML
        )
        rendered = render(template, {"name": "World"})
        assert render_to_html(rendered) == "<b>World</b>"

    async def test_markdown_format_is_converted_to_actual_html(self) -> None:
        template = to_shared_template(
            template_key="t1", body_template="**bold**", template_format=TemplateFormat.MARKDOWN
        )
        rendered = render(template, {})
        assert render_to_html(rendered) == "<p><strong>bold</strong></p>"

    async def test_plain_text_is_wrapped_in_pre_with_html_escaping(self) -> None:
        template = to_shared_template(
            template_key="t1",
            body_template="<script>alert(1)</script> & more",
            template_format=TemplateFormat.PLAIN_TEXT,
        )
        rendered = render(template, {})
        assert (
            render_to_html(rendered)
            == "<pre>&lt;script&gt;alert(1)&lt;/script&gt; &amp; more</pre>"
        )
