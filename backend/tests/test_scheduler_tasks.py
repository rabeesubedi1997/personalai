"""Unit tests for each ScheduledTask directly against a db_session —
no need to wait for the real interval or run the background loop."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval, ApprovalStatus
from app.models.notification import Notification
from app.models.request import Request, RequestStatus
from app.scheduler.tasks import (
    FailedAgentRunFollowUpTask,
    StalePendingApprovalReminderTask,
    StaleRequestEscalationTask,
)
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def test_failed_agent_run_triggers_notification_once(db_session):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    run = AgentRun(
        tenant_id=tenant_id,
        user_id=user_id,
        agent_name="general_assistant",
        request_text="do something",
        status=AgentRunStatus.FAILED,
        error="provider unavailable",
    )
    db_session.add(run)
    await db_session.commit()

    task = FailedAgentRunFollowUpTask()
    result = await task.run(db_session)
    assert result == {"checked": 1, "notified": 1}

    notifications = (
        await db_session.execute(select(Notification).where(Notification.user_id == user_id))
    ).scalars().all()
    assert len(notifications) == 1
    assert "failed" in notifications[0].message.lower()
    assert "provider unavailable" in notifications[0].message

    # Second run must not re-notify — escalation_notified is now True.
    result2 = await task.run(db_session)
    assert result2 == {"checked": 0, "notified": 0}


async def test_completed_runs_are_never_flagged(db_session):
    run = AgentRun(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        agent_name="general_assistant",
        request_text="hi",
        status=AgentRunStatus.COMPLETED,
    )
    db_session.add(run)
    await db_session.commit()

    result = await FailedAgentRunFollowUpTask().run(db_session)
    assert result == {"checked": 0, "notified": 0}


async def test_stale_pending_approval_reminder_sent_once(db_session):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    run = AgentRun(
        tenant_id=tenant_id,
        user_id=user_id,
        agent_name="general_assistant",
        request_text="cancel booking BK-1",
        status=AgentRunStatus.AWAITING_APPROVAL,
    )
    db_session.add(run)
    await db_session.flush()

    old_time = datetime.now(timezone.utc) - timedelta(
        minutes=settings.approval_reminder_after_minutes + 5
    )
    approval = Approval(
        tenant_id=tenant_id,
        agent_run_id=run.id,
        agent_name="general_assistant",
        tool_name="cancel_booking",
        arguments={"booking_id": "BK-1"},
        allowed_tool_names=["cancel_booking"],
        created_at=old_time,
    )
    db_session.add(approval)
    await db_session.commit()

    task = StalePendingApprovalReminderTask()
    result = await task.run(db_session)
    assert result == {"checked": 1, "notified": 1}

    result2 = await task.run(db_session)
    assert result2 == {"checked": 0, "notified": 0}


async def test_fresh_pending_approval_not_reminded_yet(db_session):
    tenant_id = uuid.uuid4()
    approval = Approval(
        tenant_id=tenant_id,
        agent_run_id=None,
        agent_name="general_assistant",
        tool_name="cancel_booking",
        arguments={"booking_id": "BK-2"},
        allowed_tool_names=["cancel_booking"],
    )  # created_at defaults to now — not stale yet
    db_session.add(approval)
    await db_session.commit()

    result = await StalePendingApprovalReminderTask().run(db_session)
    assert result == {"checked": 0, "notified": 0}


async def test_stale_request_auto_escalated(db_session):
    tenant_id = uuid.uuid4()
    req = Request(
        tenant_id=tenant_id,
        request_type="service_booking",
        status=RequestStatus.UNDERSTANDING,
        status_history=[],
    )
    db_session.add(req)
    await db_session.commit()

    # Force it stale by directly backdating updated_at (TimestampMixin sets
    # it on insert; simulate time passing without a real sleep).
    old_time = datetime.now(timezone.utc) - timedelta(
        hours=settings.request_stale_after_hours + 1
    )
    req.updated_at = old_time
    db_session.add(req)
    await db_session.commit()

    task = StaleRequestEscalationTask()
    result = await task.run(db_session)
    assert result == {"checked": 1, "escalated": 1}

    await db_session.refresh(req)
    assert req.status == RequestStatus.ESCALATED
    assert req.status_history[-1]["to"] == "escalated"


async def test_fresh_request_not_escalated(db_session):
    req = Request(
        tenant_id=uuid.uuid4(),
        request_type="service_booking",
        status=RequestStatus.UNDERSTANDING,
        status_history=[],
    )
    db_session.add(req)
    await db_session.commit()

    result = await StaleRequestEscalationTask().run(db_session)
    assert result == {"checked": 0, "escalated": 0}


async def test_completed_request_never_escalated_even_if_old(db_session):
    req = Request(
        tenant_id=uuid.uuid4(),
        request_type="service_booking",
        status=RequestStatus.COMPLETED,
        status_history=[],
    )
    db_session.add(req)
    await db_session.commit()
    req.updated_at = datetime.now(timezone.utc) - timedelta(days=30)
    db_session.add(req)
    await db_session.commit()

    result = await StaleRequestEscalationTask().run(db_session)
    assert result == {"checked": 0, "escalated": 0}
