"""ChannelConfigService: always-on channels, and per-channel configuration.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import pytest

from app.models.enums import NotificationChannelKind
from app.services.channel import ChannelConfigService

pytestmark = pytest.mark.asyncio


class TestIsEnabled:
    async def test_email_is_always_enabled_with_no_config_row(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        assert await channel_service.is_enabled(organization_id, NotificationChannelKind.EMAIL) is True

    async def test_in_app_is_always_enabled_with_no_config_row(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        assert await channel_service.is_enabled(organization_id, NotificationChannelKind.IN_APP) is True

    async def test_email_is_enabled_even_if_a_disabled_config_row_exists(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        await channel_service.set_config(organization_id, NotificationChannelKind.EMAIL, enabled=False)
        assert await channel_service.is_enabled(organization_id, NotificationChannelKind.EMAIL) is True

    async def test_other_channel_is_disabled_with_no_config_row(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        assert (
            await channel_service.is_enabled(organization_id, NotificationChannelKind.WEBHOOK) is False
        )

    async def test_other_channel_is_enabled_when_config_row_says_so(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        await channel_service.set_config(organization_id, NotificationChannelKind.WEBHOOK, enabled=True)
        assert (
            await channel_service.is_enabled(organization_id, NotificationChannelKind.WEBHOOK) is True
        )

    async def test_other_channel_is_disabled_when_config_row_says_so(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        await channel_service.set_config(organization_id, NotificationChannelKind.SLACK, enabled=False)
        assert await channel_service.is_enabled(organization_id, NotificationChannelKind.SLACK) is False


class TestSetConfig:
    async def test_creates_a_new_row_when_none_exists(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        created = await channel_service.set_config(
            organization_id,
            NotificationChannelKind.SLACK,
            enabled=True,
            config={"webhook_url": "https://example.com/a"},
            description="Team alerts",
        )
        assert created.channel == NotificationChannelKind.SLACK
        assert created.enabled is True
        assert created.config == {"webhook_url": "https://example.com/a"}
        assert created.description == "Team alerts"

    async def test_second_call_replaces_the_existing_row_rather_than_creating_another(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        first = await channel_service.set_config(
            organization_id,
            NotificationChannelKind.SLACK,
            enabled=True,
            config={"webhook_url": "https://example.com/a"},
        )
        second = await channel_service.set_config(
            organization_id,
            NotificationChannelKind.SLACK,
            enabled=False,
            config={"webhook_url": "https://example.com/b"},
        )
        assert second.id == first.id

        configs = await channel_service.list_configs(organization_id)
        slack_rows = [row for row in configs if row.channel == NotificationChannelKind.SLACK]
        assert len(slack_rows) == 1
        assert slack_rows[0].enabled is False
        assert slack_rows[0].config == {"webhook_url": "https://example.com/b"}

    async def test_description_is_updated_when_explicitly_provided_on_replace(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        await channel_service.set_config(
            organization_id, NotificationChannelKind.SLACK, description="Initial"
        )
        updated = await channel_service.set_config(
            organization_id, NotificationChannelKind.SLACK, description="Replaced"
        )
        assert updated.description == "Replaced"

    async def test_description_is_left_unchanged_when_not_provided_on_replace(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        await channel_service.set_config(
            organization_id, NotificationChannelKind.SLACK, description="Keep me"
        )
        updated = await channel_service.set_config(organization_id, NotificationChannelKind.SLACK)
        assert updated.description == "Keep me"

    async def test_defaults_to_enabled_true_and_empty_config(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        created = await channel_service.set_config(organization_id, NotificationChannelKind.WEBHOOK)
        assert created.enabled is True
        assert created.config == {}


class TestGetConfig:
    async def test_returns_none_when_no_config_exists(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        found = await channel_service.get_config(organization_id, NotificationChannelKind.WEBHOOK)
        assert found is None

    async def test_returns_the_configured_row(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        created = await channel_service.set_config(organization_id, NotificationChannelKind.WEBHOOK)
        found = await channel_service.get_config(organization_id, NotificationChannelKind.WEBHOOK)
        assert found is not None
        assert found.id == created.id


class TestListConfigs:
    async def test_returns_every_configured_channel(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        await channel_service.set_config(organization_id, NotificationChannelKind.WEBHOOK)
        await channel_service.set_config(organization_id, NotificationChannelKind.SLACK)

        configs = await channel_service.list_configs(organization_id)
        channels = {row.channel for row in configs}
        assert channels == {NotificationChannelKind.WEBHOOK, NotificationChannelKind.SLACK}

    async def test_returns_empty_list_when_nothing_is_configured(
        self, channel_service: ChannelConfigService, organization_id
    ) -> None:
        configs = await channel_service.list_configs(organization_id)
        assert configs == []
