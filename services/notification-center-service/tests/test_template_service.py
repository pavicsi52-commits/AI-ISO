"""TemplateService: creation, versioning-on-content-change, and preview.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import NotificationCategory, TemplateFormat
from app.services.template import TemplateService

pytestmark = pytest.mark.asyncio

_INVALID_BODY = "{{ unclosed"


class TestCreate:
    async def test_creates_with_current_version_one(
        self, template_service: TemplateService, organization_id
    ) -> None:
        created = await template_service.create(
            organization_id,
            template_key="job.failed",
            name="Job failed",
            body_template="Job {{ job_name }} failed.",
        )
        assert created.current_version == 1
        assert created.template_key == "job.failed"
        assert created.body_template == "Job {{ job_name }} failed."

    async def test_raises_template_render_error_for_invalid_body_syntax(
        self, template_service: TemplateService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await template_service.create(
                organization_id,
                template_key="bad.template",
                name="Bad template",
                body_template=_INVALID_BODY,
            )

    async def test_does_not_persist_a_row_when_validation_fails(
        self, template_service: TemplateService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await template_service.create(
                organization_id,
                template_key="bad.template",
                name="Bad template",
                body_template=_INVALID_BODY,
            )
        remaining = await template_service.list_templates(organization_id)
        assert remaining == []

    async def test_raises_template_render_error_for_invalid_subject_syntax(
        self, template_service: TemplateService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await template_service.create(
                organization_id,
                template_key="bad.subject",
                name="Bad subject",
                body_template="Fine body.",
                subject_template=_INVALID_BODY,
            )

    async def test_sets_created_by_from_actor_id(
        self, template_service: TemplateService, organization_id
    ) -> None:
        actor_id = uuid4()
        created = await template_service.create(
            organization_id,
            template_key="job.failed",
            name="Job failed",
            body_template="Job failed.",
            actor_id=str(actor_id),
        )
        assert created.created_by == actor_id


class TestGet:
    async def test_raises_not_found_for_a_missing_template(
        self, template_service: TemplateService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await template_service.get(organization_id, uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template()
        with pytest.raises(NotFoundError):
            await template_service.get(uuid4(), created.id)


class TestGetByKey:
    async def test_returns_none_when_no_template_matches(
        self, template_service: TemplateService, organization_id
    ) -> None:
        found = await template_service.get_by_key(organization_id, "does.not.exist")
        assert found is None

    async def test_returns_the_matching_template(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(template_key="job.failed")
        found = await template_service.get_by_key(organization_id, "job.failed")
        assert found is not None
        assert found.id == created.id

    async def test_is_scoped_by_locale(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        await make_template(template_key="job.failed", locale="en")
        found = await template_service.get_by_key(organization_id, "job.failed", locale="fr")
        assert found is None


class TestListTemplates:
    async def test_lists_every_template_in_the_org(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(template_key="job.failed")
        found = await template_service.list_templates(organization_id)
        ids = {one.id for one in found}
        assert created.id in ids

    async def test_filters_by_is_active(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        active = await make_template(template_key="active.one")
        inactive = await make_template(template_key="inactive.one")
        await template_service.update(organization_id, inactive.id, is_active=False)

        only_active = await template_service.list_templates(organization_id, is_active=True)
        ids = {one.id for one in only_active}
        assert active.id in ids
        assert inactive.id not in ids


class TestUpdate:
    async def test_changing_body_creates_a_version_of_the_old_content_and_bumps_version(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Hello {{ name }}.")
        updated = await template_service.update(
            organization_id, created.id, body_template="Hi there {{ name }}."
        )
        assert updated.current_version == 2
        assert updated.body_template == "Hi there {{ name }}."

        versions = await template_service.list_versions(organization_id, created.id)
        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].body_template == "Hello {{ name }}."

    async def test_repassing_the_identical_body_does_not_version(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Hello {{ name }}.")
        updated = await template_service.update(
            organization_id, created.id, body_template="Hello {{ name }}."
        )
        assert updated.current_version == 1

        versions = await template_service.list_versions(organization_id, created.id)
        assert versions == []

    async def test_repassing_the_current_body_after_a_real_change_does_not_double_version(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Hello {{ name }}.")
        await template_service.update(organization_id, created.id, body_template="Hi {{ name }}.")

        # Second update passes the *now-current* body unchanged.
        updated_again = await template_service.update(
            organization_id, created.id, body_template="Hi {{ name }}."
        )
        assert updated_again.current_version == 2

        versions = await template_service.list_versions(organization_id, created.id)
        assert len(versions) == 1

    async def test_updating_only_name_never_versions(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Hello {{ name }}.")
        updated = await template_service.update(organization_id, created.id, name="New name")
        assert updated.current_version == 1
        assert updated.name == "New name"

        versions = await template_service.list_versions(organization_id, created.id)
        assert versions == []

    async def test_updating_description_category_and_is_active_never_versions(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Hello {{ name }}.")
        updated = await template_service.update(
            organization_id,
            created.id,
            description="A description",
            category=NotificationCategory.REMINDER,
            is_active=False,
        )
        assert updated.current_version == 1
        assert updated.description == "A description"
        assert updated.category == NotificationCategory.REMINDER
        assert updated.is_active is False

    async def test_changing_subject_template_versions(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Body.", subject_template="Old subject")
        updated = await template_service.update(
            organization_id, created.id, subject_template="New subject"
        )
        assert updated.current_version == 2
        versions = await template_service.list_versions(organization_id, created.id)
        assert versions[0].subject_template == "Old subject"

    async def test_changing_format_versions(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Body.")
        assert created.format == TemplateFormat.PLAIN_TEXT
        updated = await template_service.update(
            organization_id, created.id, format=TemplateFormat.HTML
        )
        assert updated.current_version == 2
        assert updated.format == TemplateFormat.HTML

    async def test_raises_template_render_error_when_new_body_syntax_is_invalid(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Hello {{ name }}.")
        with pytest.raises(ValidationError):
            await template_service.update(organization_id, created.id, body_template=_INVALID_BODY)

    async def test_raises_not_found_for_a_missing_template(
        self, template_service: TemplateService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await template_service.update(organization_id, uuid4(), name="Nope")

    async def test_silently_ignores_a_non_editable_field(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Hello {{ name }}.")
        updated = await template_service.update(
            organization_id, created.id, template_key="not.editable"
        )
        assert updated.template_key == created.template_key

    async def test_sets_updated_by_from_actor_id(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Hello {{ name }}.")
        actor_id = uuid4()
        updated = await template_service.update(
            organization_id, created.id, actor_id=str(actor_id), name="Renamed"
        )
        assert updated.updated_by == actor_id


class TestListVersions:
    async def test_returns_empty_list_for_a_never_updated_template(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template()
        versions = await template_service.list_versions(organization_id, created.id)
        assert versions == []


class TestPreview:
    async def test_renders_current_content_against_supplied_variables(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Hi {{ name }}!")
        rendered = await template_service.preview(organization_id, created.id, {"name": "Ada"})
        assert rendered.body == "Hi Ada!"

    async def test_renders_the_current_content_not_a_historical_version(
        self, template_service: TemplateService, organization_id, make_template
    ) -> None:
        created = await make_template(body_template="Old {{ name }}.")
        await template_service.update(organization_id, created.id, body_template="New {{ name }}.")

        rendered = await template_service.preview(organization_id, created.id, {"name": "Ada"})
        assert rendered.body == "New Ada."

    async def test_raises_not_found_for_a_missing_template(
        self, template_service: TemplateService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await template_service.preview(organization_id, uuid4(), {})
