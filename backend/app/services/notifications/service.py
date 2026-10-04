"""
NotificationService: the one place application code sends a notification
from. It persists a Notification row regardless of outcome (so delivery
failures are visible and queryable, never silent) and dispatches to the
right channel provider.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationChannel, NotificationStatus
from app.services.notifications.base import NotificationChannelProvider
from app.services.notifications.channels import (
    EmailNotificationChannel,
    SmsNotificationChannel,
    WebNotificationChannel,
    WhatsAppNotificationChannel,
)

_PROVIDERS: dict[NotificationChannel, NotificationChannelProvider] = {
    NotificationChannel.WEB: WebNotificationChannel(),
    NotificationChannel.EMAIL: EmailNotificationChannel(),
    NotificationChannel.SMS: SmsNotificationChannel(),
    NotificationChannel.WHATSAPP: WhatsAppNotificationChannel(),
}


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def send(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        channel: NotificationChannel,
        subject: str,
        message: str,
        metadata: dict | None = None,
    ) -> Notification:
        provider = _PROVIDERS[channel]
        result = await provider.send(user_id=str(user_id), subject=subject, message=message)

        notification = Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            channel=channel,
            subject=subject,
            message=message,
            status=NotificationStatus.SENT if result.success else NotificationStatus.FAILED,
            notification_metadata={**(metadata or {}), "provider_message_id": result.provider_message_id},
            error=result.error,
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def list_for_user(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        unread_only: bool = False,
    ) -> list[Notification]:
        query = select(Notification).where(
            Notification.tenant_id == tenant_id, Notification.user_id == user_id
        )
        if unread_only:
            query = query.where(Notification.is_read.is_(False))
        query = query.order_by(Notification.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def mark_read(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID
    ) -> Notification | None:
        result = await self.db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
                Notification.user_id == user_id,
            )
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            return None
        notification.is_read = True
        await self.db.commit()
        await self.db.refresh(notification)
        return notification
