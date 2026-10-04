import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.notifications import NotificationOut
from app.security.deps import get_current_user
from app.services.notifications.service import NotificationService

router = APIRouter()


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationOut]:
    service = NotificationService(db)
    notifications = await service.list_for_user(
        tenant_id=current_user.tenant_id, user_id=current_user.id, unread_only=unread_only
    )
    return [NotificationOut.from_model(n) for n in notifications]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationOut:
    service = NotificationService(db)
    notification = await service.mark_read(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        notification_id=notification_id,
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return NotificationOut.from_model(notification)
