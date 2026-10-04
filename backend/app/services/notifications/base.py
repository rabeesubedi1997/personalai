"""
Notification channel abstraction (spec Section 22). The rest of the app
depends only on NotificationChannelProvider via NotificationService — never
on a concrete channel directly — so adding a real SMS/WhatsApp provider
later (Twilio, Meta's WhatsApp Business API, ...) means writing one new
class, not touching call sites.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class NotificationSendResult:
    success: bool
    provider_message_id: str | None = None
    error: str | None = None


class NotificationChannelProvider(ABC):
    name: str

    @abstractmethod
    async def send(self, *, user_id: str, subject: str, message: str) -> NotificationSendResult:
        """Deliver the notification. Must return success=False with a
        clear error rather than silently pretending to have sent
        something (spec Section 47: never claim success when an action
        failed)."""
