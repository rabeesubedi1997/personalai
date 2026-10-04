"""
Concrete notification channels.

WEB is the only channel that's genuinely "real" here: an in-app
notification's delivery mechanism IS the database row — there's nothing
external to call, so there's nothing to mock.

EMAIL / SMS / WHATSAPP have no real provider configured (no SMTP
credentials, no Twilio/WhatsApp Business API access — none invented, per
the master spec's rule against fabricating credentials). They log what
would have been sent and report success, clearly labeled as dev stubs —
the same "mock now, swap later" pattern used for the Tolemate/Ghar
Nepal/Paradise Nepal connectors. Swapping in a real provider means writing
one new class implementing NotificationChannelProvider; nothing else
changes.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.services.notifications.base import NotificationChannelProvider, NotificationSendResult

logger = get_logger(__name__)


class WebNotificationChannel(NotificationChannelProvider):
    """The in-app notification IS the delivery — this always 'succeeds' in
    the sense that there's nothing external to fail. NotificationService
    still persists the row regardless of channel; this class exists mainly
    so WEB fits the same interface as the others."""

    name = "web"

    async def send(self, *, user_id: str, subject: str, message: str) -> NotificationSendResult:
        return NotificationSendResult(success=True)


class _DevStubChannel(NotificationChannelProvider):
    """Shared behavior for channels with no real provider configured yet."""

    async def send(self, *, user_id: str, subject: str, message: str) -> NotificationSendResult:
        logger.info(
            "notification_dev_stub_send",
            channel=self.name,
            user_id=user_id,
            subject=subject,
        )
        return NotificationSendResult(success=True, provider_message_id=f"dev-stub-{self.name}")


class EmailNotificationChannel(_DevStubChannel):
    name = "email"


class SmsNotificationChannel(_DevStubChannel):
    name = "sms"


class WhatsAppNotificationChannel(_DevStubChannel):
    name = "whatsapp"
