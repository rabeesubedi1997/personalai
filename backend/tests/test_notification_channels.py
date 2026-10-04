import pytest

from app.services.notifications.channels import (
    EmailNotificationChannel,
    SmsNotificationChannel,
    WebNotificationChannel,
    WhatsAppNotificationChannel,
)

pytestmark = pytest.mark.asyncio


async def test_web_channel_always_succeeds():
    channel = WebNotificationChannel()
    result = await channel.send(user_id="u1", subject="hi", message="hello")
    assert result.success is True


async def test_dev_stub_channels_report_success_with_marker():
    for channel in [EmailNotificationChannel(), SmsNotificationChannel(), WhatsAppNotificationChannel()]:
        result = await channel.send(user_id="u1", subject="hi", message="hello")
        assert result.success is True
        assert result.provider_message_id == f"dev-stub-{channel.name}"
