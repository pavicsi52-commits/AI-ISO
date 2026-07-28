"""API-layer tests through the real ASGI app.

The app is started through its genuine lifespan -- database, cache,
events, notifications, object storage, JWT key loading -- and every
request goes through the real middleware stack, real authentication,
and real dependency graph. Only the outbound HTTP transport is stubbed,
so data sources stay deterministic while everything around them is
production code.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    DistributionChannel,
    ExportFormat,
    ReportCategory,
    ReportType,
    ScheduleFrequency,
    TemplateStatus,
)
from tests.conftest import (
    SIMPLE_DEFINITION,
    AuthHeadersFn,
    make_job,
    make_template,
)

CALLER = uuid.uuid4()


@pytest.fixture
def headers(auth_headers: AuthHeadersFn) -> dict[str, str]:
    return auth_headers(CALLER)


def data_of(payload: dict[str, Any]) -> Any:
    """The envelope's ``data`` field, asserting the envelope shape."""
    assert payload["success"] is True
    assert "meta" in payload
    return payload["data"]


class TestAuthentication:
    """Every business route is authenticated; health probes are not."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", f"/reports?organization_id={uuid.uuid4()}"),
            ("post", "/reports"),
            ("get", f"/reports/{uuid.uuid4()}"),
            ("put", f"/reports/{uuid.uuid4()}"),
            ("delete", f"/reports/{uuid.uuid4()}"),
            ("post", "/reports/generate"),
            ("post", "/reports/export"),
            ("get", f"/reports/history?organization_id={uuid.uuid4()}"),
            ("get", f"/reports/statistics?organization_id={uuid.uuid4()}"),
            ("get", f"/reports/templates?organization_id={uuid.uuid4()}"),
            ("post", "/reports/templates"),
            ("get", f"/reports/templates/{uuid.uuid4()}"),
            ("post", f"/reports/templates/{uuid.uuid4()}/approve"),
            ("post", "/reports/schedule"),
            ("get", f"/reports/schedules?organization_id={uuid.uuid4()}"),
            ("get", f"/reports/archive?organization_id={uuid.uuid4()}"),
            ("post", "/reports/archive"),
            ("get", f"/reports/categories?organization_id={uuid.uuid4()}"),
            ("post", "/reports/categories"),
            ("get", f"/reports/distributions?organization_id={uuid.uuid4()}"),
            ("get", f"/reports/exports/{uuid.uuid4()}/download"),
        ],
    )
    async def test_unauthenticated_requests_are_rejected(
        self, client: AsyncClient, method: str, path: str
    ) -> None:
        assert (await client.request(method, path, json={})).status_code == 401

    async def test_a_forged_token_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get(
            f"/reports?organization_id={uuid.uuid4()}",
            headers={"Authorization": "Bearer not.a.real.token"},
        )
        assert response.status_code == 401


class TestReportRoutes:
    async def test_create_list_get_update_delete(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org = uuid.uuid4()
        created = await client.post(
            "/reports",
            headers=headers,
            json={
                "organization_id": str(org),
                "name": "Nightly Fleet",
                "category": ReportCategory.INFRASTRUCTURE.value,
                "report_type": ReportType.SUMMARY.value,
                "default_format": ExportFormat.CSV.value,
            },
        )
        assert created.status_code == 201
        report = data_of(created.json())
        assert report["owner_id"] == str(CALLER)

        listed = await client.get(f"/reports?organization_id={org}", headers=headers)
        assert len(data_of(listed.json())) == 1

        fetched = await client.get(f"/reports/{report['id']}", headers=headers)
        assert data_of(fetched.json())["name"] == "Nightly Fleet"

        updated = await client.put(
            f"/reports/{report['id']}", headers=headers, json={"description": "Now described"}
        )
        assert data_of(updated.json())["description"] == "Now described"
        assert data_of(updated.json())["name"] == "Nightly Fleet"

        deleted = await client.delete(f"/reports/{report['id']}", headers=headers)
        assert deleted.status_code == 200
        assert (await client.get(f"/reports/{report['id']}", headers=headers)).status_code == 404

    async def test_a_malformed_filter_is_rejected(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/reports",
            headers=headers,
            json={
                "organization_id": str(uuid.uuid4()),
                "name": "Bad",
                "category": ReportCategory.CUSTOM.value,
                "report_type": ReportType.TABULAR.value,
                "filters": [{"operator": "eq", "value": "x"}],
            },
        )
        assert response.status_code == 400

    async def test_an_invalid_category_is_rejected(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/reports",
            headers=headers,
            json={
                "organization_id": str(uuid.uuid4()),
                "name": "Bad",
                "category": "not-a-category",
                "report_type": ReportType.TABULAR.value,
            },
        )
        assert response.status_code == 400

    async def test_an_unknown_report_is_404(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        assert (await client.get(f"/reports/{uuid.uuid4()}", headers=headers)).status_code == 404

    async def test_favourites(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        job = await make_job(db_session, organization_id=org)

        assert (
            await client.post(f"/reports/{job.id}/favorite", headers=headers)
        ).status_code == 201
        listed = await client.get(f"/reports/favorites/mine?organization_id={org}", headers=headers)
        assert len(data_of(listed.json())) == 1

        await client.delete(f"/reports/{job.id}/favorite", headers=headers)
        listed = await client.get(f"/reports/favorites/mine?organization_id={org}", headers=headers)
        assert data_of(listed.json()) == []


class TestTemplateRoutes:
    def _payload(self, org: uuid.UUID, **overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "organization_id": str(org),
            "name": "Fleet Report",
            "category": ReportCategory.INFRASTRUCTURE.value,
            "report_type": ReportType.SUMMARY.value,
            "definition": SIMPLE_DEFINITION,
            "parameters": [{"key": "environment", "label": "Environment", "kind": "string"}],
        }
        payload.update(overrides)
        return payload

    async def test_create_approve_and_version(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org = uuid.uuid4()
        created = await client.post("/reports/templates", headers=headers, json=self._payload(org))
        assert created.status_code == 201
        template = data_of(created.json())
        assert template["status"] == TemplateStatus.DRAFT.value
        assert template["version_number"] == "1.0.0"

        parameters = await client.get(
            f"/reports/templates/{template['id']}/parameters", headers=headers
        )
        assert [entry["key"] for entry in data_of(parameters.json())] == ["environment"]

        approved = await client.post(
            f"/reports/templates/{template['id']}/approve", headers=headers
        )
        assert data_of(approved.json())["status"] == TemplateStatus.APPROVED.value
        assert data_of(approved.json())["approved_by"] == str(CALLER)

        version = await client.post(
            f"/reports/templates/{template['id']}/versions",
            headers=headers,
            json={"definition": SIMPLE_DEFINITION},
        )
        assert data_of(version.json())["version_number"] == "1.1.0"

        versions = await client.get(
            f"/reports/templates/{template['id']}/versions", headers=headers
        )
        assert len(data_of(versions.json())) == 2

    async def test_a_malformed_definition_is_rejected(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        """Rejected at authoring time, not inside a scheduled run."""
        response = await client.post(
            "/reports/templates",
            headers=headers,
            json=self._payload(
                uuid.uuid4(),
                definition={"title": "T", "sections": [{"key": "t", "kind": "table"}]},
            ),
        )
        # The detail is deliberately sanitised out of the response and
        # logged instead, so the assertion is on the error code.
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "AIIOS-VAL-0001"

    async def test_a_duplicate_name_is_a_conflict(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org = uuid.uuid4()
        await client.post("/reports/templates", headers=headers, json=self._payload(org))
        again = await client.post("/reports/templates", headers=headers, json=self._payload(org))
        assert again.status_code == 409

    async def test_archiving_blocks_approval(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        template = await make_template(db_session, status=TemplateStatus.DRAFT)
        await client.post(f"/reports/templates/{template.id}/archive", headers=headers)
        response = await client.post(f"/reports/templates/{template.id}/approve", headers=headers)
        assert response.status_code == 409

    async def test_categories(self, client: AsyncClient, headers: dict[str, str]) -> None:
        org = uuid.uuid4()
        created = await client.post(
            "/reports/categories",
            headers=headers,
            json={
                "organization_id": str(org),
                "category": ReportCategory.CAPACITY.value,
                "slug": "cap",
                "name": "Capacity",
            },
        )
        assert created.status_code == 201

        duplicate = await client.post(
            "/reports/categories",
            headers=headers,
            json={
                "organization_id": str(org),
                "category": ReportCategory.CAPACITY.value,
                "slug": "cap",
                "name": "Capacity Again",
            },
        )
        assert duplicate.status_code == 409

        listed = await client.get(f"/reports/categories?organization_id={org}", headers=headers)
        assert len(data_of(listed.json())) == 1


class TestGenerationRoutes:
    async def test_generate_produces_downloadable_artifacts(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)

        generated = await client.post(
            "/reports/generate",
            headers=headers,
            json={
                "report_id": str(job.id),
                "export_formats": [ExportFormat.CSV.value, ExportFormat.JSON.value],
            },
        )
        assert generated.status_code == 201
        result = data_of(generated.json())
        assert result["execution"]["status"] == "succeeded"
        assert result["execution"]["row_count"] == 4
        assert len(result["exports"]) == 2
        assert result["degraded_sections"] == []

        export_id = result["exports"][0]["id"]
        downloaded = await client.get(f"/reports/exports/{export_id}/download", headers=headers)
        assert downloaded.status_code == 200
        assert downloaded.headers["content-disposition"].startswith("attachment")
        assert len(downloaded.content) > 0

    async def test_download_increments_the_counter(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        generated = await client.post(
            "/reports/generate", headers=headers, json={"report_id": str(job.id)}
        )
        export_id = data_of(generated.json())["exports"][0]["id"]
        execution_id = data_of(generated.json())["execution"]["id"]

        await client.get(f"/reports/exports/{export_id}/download", headers=headers)
        listed = await client.get(f"/reports/executions/{execution_id}/exports", headers=headers)
        assert data_of(listed.json())[0]["download_count"] == 1

    async def test_generating_from_an_unapproved_template_is_a_conflict(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org, status=TemplateStatus.DRAFT)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        response = await client.post(
            "/reports/generate", headers=headers, json={"report_id": str(job.id)}
        )
        assert response.status_code == 409

    async def test_generating_an_unknown_report_is_404(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/reports/generate", headers=headers, json={"report_id": str(uuid.uuid4())}
        )
        assert response.status_code == 404

    async def test_generate_can_archive_in_one_call(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        generated = await client.post(
            "/reports/generate",
            headers=headers,
            json={"report_id": str(job.id), "archive": True},
        )
        assert data_of(generated.json())["archive_id"] is not None

    async def test_re_export_renders_a_new_format(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """A PDF cannot be turned into a spreadsheet, so it re-renders."""
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        generated = await client.post(
            "/reports/generate", headers=headers, json={"report_id": str(job.id)}
        )
        execution_id = data_of(generated.json())["execution"]["id"]

        exported = await client.post(
            "/reports/export",
            headers=headers,
            json={"execution_id": execution_id, "export_format": ExportFormat.XLSX.value},
        )
        assert exported.status_code == 201
        assert data_of(exported.json())["export_format"] == "xlsx"

    async def test_history_records_the_run(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        await client.post("/reports/generate", headers=headers, json={"report_id": str(job.id)})

        history = await client.get(
            f"/reports/history?organization_id={org}&report_id={job.id}", headers=headers
        )
        assert [entry["event"] for entry in data_of(history.json())] == ["generated"]

    async def test_statistics_reflect_the_run(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        await client.post("/reports/generate", headers=headers, json={"report_id": str(job.id)})

        stats = await client.get(
            f"/reports/statistics?organization_id={org}&recompute=true", headers=headers
        )
        snapshot = data_of(stats.json())
        assert snapshot["total_executions"] == 1
        assert snapshot["successful_executions"] == 1
        assert snapshot["computed_at"]


class TestScheduleRoutes:
    async def test_schedule_lifecycle(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        job = await make_job(db_session, organization_id=org)

        created = await client.post(
            "/reports/schedule",
            headers=headers,
            json={
                "organization_id": str(org),
                "report_id": str(job.id),
                "frequency": ScheduleFrequency.DAILY.value,
                "starts_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                "timezone": "Europe/Berlin",
            },
        )
        assert created.status_code == 201
        schedule = data_of(created.json())
        assert schedule["next_run_at"] is not None
        assert schedule["timezone"] == "Europe/Berlin"

        listed = await client.get(f"/reports/schedules?organization_id={org}", headers=headers)
        assert len(data_of(listed.json())) == 1

        updated = await client.put(
            f"/reports/schedules/{schedule['id']}",
            headers=headers,
            json={"frequency": ScheduleFrequency.HOURLY.value},
        )
        assert data_of(updated.json())["frequency"] == "hourly"

        deleted = await client.delete(f"/reports/schedules/{schedule['id']}", headers=headers)
        assert deleted.status_code == 200

    async def test_an_invalid_timezone_is_rejected(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        job = await make_job(db_session, organization_id=org)
        response = await client.post(
            "/reports/schedule",
            headers=headers,
            json={
                "organization_id": str(org),
                "report_id": str(job.id),
                "frequency": ScheduleFrequency.DAILY.value,
                "starts_at": datetime.now(UTC).isoformat(),
                "timezone": "Mars/Olympus",
            },
        )
        assert response.status_code == 400

    async def test_a_cron_schedule_without_an_expression_is_rejected(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        job = await make_job(db_session, organization_id=org)
        response = await client.post(
            "/reports/schedule",
            headers=headers,
            json={
                "organization_id": str(org),
                "report_id": str(job.id),
                "frequency": ScheduleFrequency.CRON.value,
                "starts_at": datetime.now(UTC).isoformat(),
            },
        )
        assert response.status_code == 400

    async def test_scheduling_an_unknown_report_is_404(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/reports/schedule",
            headers=headers,
            json={
                "organization_id": str(uuid.uuid4()),
                "report_id": str(uuid.uuid4()),
                "frequency": ScheduleFrequency.DAILY.value,
                "starts_at": datetime.now(UTC).isoformat(),
            },
        )
        assert response.status_code == 404


class TestDistributionRoutes:
    async def _export_id(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> tuple[str, uuid.UUID]:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        generated = await client.post(
            "/reports/generate", headers=headers, json={"report_id": str(job.id)}
        )
        return data_of(generated.json())["exports"][0]["id"], job.id

    async def test_recipients_are_validated_and_listed(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        job = await make_job(db_session, organization_id=org)

        bad = await client.post(
            f"/reports/{job.id}/recipients",
            headers=headers,
            json={
                "organization_id": str(org),
                "channel": DistributionChannel.EMAIL.value,
                "target": "not-an-email",
            },
        )
        assert bad.status_code == 400

        good = await client.post(
            f"/reports/{job.id}/recipients",
            headers=headers,
            json={
                "organization_id": str(org),
                "channel": DistributionChannel.EMAIL.value,
                "target": "ops@example.com",
            },
        )
        assert good.status_code == 201

        listed = await client.get(f"/reports/{job.id}/recipients", headers=headers)
        assert len(data_of(listed.json())) == 1

        removed = await client.delete(
            f"/reports/recipients/{data_of(good.json())['id']}", headers=headers
        )
        assert removed.status_code == 200

    async def test_a_shared_link_is_minted_once_and_redeemable(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """The token is a bearer credential; it must not appear in listings."""
        export_id, _job_id = await self._export_id(client, headers, db_session)

        shared = await client.post(f"/reports/exports/{export_id}/share", headers=headers)
        assert shared.status_code == 201
        token = data_of(shared.json())["share_token"]
        assert token

        listed = await client.get(f"/reports/exports/{export_id}/distributions", headers=headers)
        assert "share_token" not in data_of(listed.json())[0]

        # Redemption is deliberately unauthenticated.
        downloaded = await client.get(f"/reports/shared/{token}")
        assert downloaded.status_code == 200
        assert len(downloaded.content) > 0

    async def test_an_unknown_share_token_is_404(self, client: AsyncClient) -> None:
        assert (await client.get("/reports/shared/not-a-real-token")).status_code == 404

    async def test_distribution_attempts_are_listed(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        export_id, _job_id = await self._export_id(client, headers, db_session)
        await client.post(
            f"/reports/exports/{export_id}/distribute",
            headers=headers,
            json={"channel": DistributionChannel.DOWNLOAD.value, "target": "n/a"},
        )
        listed = await client.get(f"/reports/exports/{export_id}/distributions", headers=headers)
        assert len(data_of(listed.json())) == 1


class TestArchiveRoutes:
    async def _archive(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> dict[str, Any]:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        generated = await client.post(
            "/reports/generate", headers=headers, json={"report_id": str(job.id)}
        )
        export_id = data_of(generated.json())["exports"][0]["id"]
        archived = await client.post(
            "/reports/archive",
            headers=headers,
            json={"export_id": export_id, "title": "Nightly Fleet"},
        )
        assert archived.status_code == 201
        archive: dict[str, Any] = data_of(archived.json())
        return archive

    async def test_archive_search_and_download(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        archive = await self._archive(client, headers, db_session)
        assert archive["archive_version"] == 1
        assert archive["retention_until"] is not None

        downloaded = await client.get(f"/reports/archive/{archive['id']}/download", headers=headers)
        assert downloaded.status_code == 200
        assert len(downloaded.content) == archive["size_bytes"]

    async def test_purging_inside_retention_is_refused(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        archive = await self._archive(client, headers, db_session)
        response = await client.delete(f"/reports/archive/{archive['id']}", headers=headers)
        assert response.status_code == 409

    async def test_restore_creates_a_new_export(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        archive = await self._archive(client, headers, db_session)
        restored = await client.post(f"/reports/archive/{archive['id']}/restore", headers=headers)
        assert restored.status_code == 200
        assert data_of(restored.json())["status"] == "restored"

    async def test_archiving_an_unknown_export_is_404(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/reports/archive",
            headers=headers,
            json={"export_id": str(uuid.uuid4()), "title": "X"},
        )
        assert response.status_code == 404

    async def test_a_short_retention_can_be_requested(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        generated = await client.post(
            "/reports/generate", headers=headers, json={"report_id": str(job.id)}
        )
        export_id = data_of(generated.json())["exports"][0]["id"]
        archived = await client.post(
            "/reports/archive",
            headers=headers,
            json={"export_id": export_id, "title": "Short", "retention_days": 1},
        )
        retention = datetime.fromisoformat(data_of(archived.json())["retention_until"])
        assert retention < datetime.now(UTC) + timedelta(days=2)
