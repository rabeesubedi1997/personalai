"""
Notification model (spec Section 22). One record per notification attempt,
regardless of channel — a web (in-app) notification IS this row (its
existence is the delivery); email/SMS/WhatsApp are external sends this row
tracks the outcome of.
"""
import enum
import uuid

from sqlalchemy import JSON, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class NotificationChannel(str, enum.Enum):
    WEB = "web"
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"


class NotificationStatus(str, enum.Enum):
    SENT = "sent"
    FAILED = "failed"


class Notification(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    channel: Mapped[NotificationChannel] = mapped_column(Enum(NotificationChannel), index=True)
    subject: Mapped[str] = mapped_column(String(255), default="")
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[NotificationStatus] = mapped_column(Enum(NotificationStatus))
    is_read: Mapped[bool] = mapped_column(default=False)
    notification_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
