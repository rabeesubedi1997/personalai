import uuid

import pytest

from app.models.notification import NotificationChannel, NotificationStatus
from app.services.notifications.service import NotificationService

pytestmark = pytest.mark.asyncio


async def test_send_persists_notification(db_session):
    service = NotificationService(db_session)
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    notification = await service.send(
        tenant_id=tenant_id,
        user_id=user_id,
        channel=NotificationChannel.WEB,
        subject="Test",
        message="Hello there",
    )
    assert notification.status == NotificationStatus.SENT
    assert notification.is_read is False


async def test_list_for_user_filters_unread(db_session):
    service = NotificationService(db_session)
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    n1 = await service.send(
        tenant_id=tenant_id, user_id=user_id, channel=NotificationChannel.WEB,
        subject="A", message="a",
    )
    await service.send(
        tenant_id=tenant_id, user_id=user_id, channel=NotificationChannel.WEB,
        subject="B", message="b",
    )

    await service.mark_read(tenant_id=tenant_id, user_id=user_id, notification_id=n1.id)

    all_notifications = await service.list_for_user(tenant_id=tenant_id, user_id=user_id)
    unread = await service.list_for_user(tenant_id=tenant_id, user_id=user_id, unread_only=True)
    assert len(all_notifications) == 2
    assert len(unread) == 1
    assert unread[0].subject == "B"


async def test_list_for_user_is_tenant_isolated(db_session):
    service = NotificationService(db_session)
    user_id = uuid.uuid4()
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    await service.send(
        tenant_id=tenant_a, user_id=user_id, channel=NotificationChannel.WEB,
        subject="A", message="a",
    )

    results = await service.list_for_user(tenant_id=tenant_b, user_id=user_id)
    assert results == []
