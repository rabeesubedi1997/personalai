import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.notification import NotificationChannel, NotificationStatus


class NotificationOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    channel: NotificationChannel
    subject: str
    message: str
    status: NotificationStatus
    is_read: bool
    metadata: dict[str, Any]
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, n) -> "NotificationOut":
        return cls(
            id=n.id,
            tenant_id=n.tenant_id,
            user_id=n.user_id,
            channel=n.channel,
            subject=n.subject,
            message=n.message,
            status=n.status,
            is_read=n.is_read,
            metadata=n.notification_metadata,
            error=n.error,
            created_at=n.created_at,
        )
