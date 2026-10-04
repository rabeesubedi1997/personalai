"""
Concrete scheduled tasks (spec Section 21's morning-check examples, made
generic and business-agnostic): failed agent runs, stale pending
approvals, and requests that haven't moved. All three work identically
regardless of which business (Tolemate/Ghar Nepal/Paradise Nepal/future)
produced the underlying row — same principle proven in
tests/test_multi_business_generality.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval, ApprovalStatus
from app.models.audit_log import AuditLog
from app.models.notification import NotificationChannel
from app.models.request import TERMINAL_STATUSES, Request, RequestStatus
from app.scheduler.base import ScheduledTask
from app.services.notifications.service import NotificationService
from app.services.request_engine import RequestEngine

logger = get_logger(__name__)

_FAILED_STATUSES = {AgentRunStatus.FAILED, AgentRunStatus.MAX_ITERATIONS_REACHED}


class FailedAgentRunFollowUpTask(ScheduledTask):
    """spec: 'Every morning: check failed bookings / failed integrations.'
    Generalized: any failed or limit-exhausted agent run gets its triggering
    user notified, once."""

    name = "failed_agent_run_follow_up"

    async def run(self, db: AsyncSession) -> dict:
        result = await db.execute(
            select(AgentRun).where(
                AgentRun.status.in_(_FAILED_STATUSES),
                AgentRun.escalation_notified.is_(False),
            )
        )
        runs = result.scalars().all()
        notified = 0
        for run in runs:
            service = NotificationService(db)
            await service.send(
                tenant_id=run.tenant_id,
                user_id=run.user_id,
                channel=NotificationChannel.WEB,
                subject="An agent run needs attention",
                message=(
                    f"Your request to '{run.agent_name}' ({run.request_text[:80]!r}) "
                    f"ended with status '{run.status.value}'"
                    + (f": {run.error}" if run.error else ".")
                ),
                metadata={"agent_run_id": str(run.id)},
            )
            run.escalation_notified = True
            notified += 1
        if runs:
            await db.commit()
        return {"checked": len(runs), "notified": notified}


class StalePendingApprovalReminderTask(ScheduledTask):
    """spec: 'Every hour: check pending approvals.' A PENDING approval
    older than APPROVAL_REMINDER_AFTER_MINUTES gets its requester reminded,
    once — not re-sent every tick."""

    name = "stale_pending_approval_reminder"

    async def run(self, db: AsyncSession) -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=settings.approval_reminder_after_minutes
        )
        result = await db.execute(
            select(Approval).where(
                Approval.status == ApprovalStatus.PENDING,
                Approval.reminder_sent.is_(False),
                Approval.created_at < cutoff,
            )
        )
        approvals = result.scalars().all()
        notified = 0
        for approval in approvals:
            requester_id = await self._requester_user_id(db, approval)
            if requester_id is None:
                # No known requester (approval has no agent_run_id, or that
                # run is gone) — nothing to send and no safe fallback user,
                # so leave reminder_sent False and let it surface via
                # GET /api/v1/approvals instead. Logged, not silently lost.
                logger.warning("approval_reminder_no_requester", approval_id=str(approval.id))
                continue
            service = NotificationService(db)
            await service.send(
                tenant_id=approval.tenant_id,
                user_id=requester_id,
                channel=NotificationChannel.WEB,
                subject="Approval still pending",
                message=(
                    f"'{approval.tool_name}' has been waiting for approval for over "
                    f"{settings.approval_reminder_after_minutes} minutes."
                ),
                metadata={"approval_id": str(approval.id)},
            )
            approval.reminder_sent = True
            notified += 1
        if notified:
            await db.commit()
        return {"checked": len(approvals), "notified": notified}

    @staticmethod
    async def _requester_user_id(db: AsyncSession, approval: Approval):
        if approval.agent_run_id is None:
            return None
        result = await db.execute(
            select(AgentRun.user_id).where(AgentRun.id == approval.agent_run_id)
        )
        return result.scalar_one_or_none()


class StaleRequestEscalationTask(ScheduledTask):
    """spec: 'Every day: report unresolved issues.' A Request stuck in a
    non-terminal state with no update for REQUEST_STALE_AFTER_HOURS is
    auto-escalated via the same RequestEngine state machine every request
    already uses — no business-specific logic needed."""

    name = "stale_request_escalation"

    async def run(self, db: AsyncSession) -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.request_stale_after_hours)
        result = await db.execute(
            select(Request).where(
                Request.status.not_in(TERMINAL_STATUSES),
                Request.updated_at < cutoff,
            )
        )
        requests = result.scalars().all()
        escalated = 0
        for req in requests:
            RequestEngine.transition(
                req,
                RequestStatus.ESCALATED,
                note=f"Auto-escalated: no update for over {settings.request_stale_after_hours}h.",
            )
            db.add(
                AuditLog(
                    tenant_id=req.tenant_id,
                    event_type="request_auto_escalated",
                    actor="scheduler",
                    status="escalated",
                    detail={"request_id": str(req.id), "request_type": req.request_type},
                )
            )
            escalated += 1
        if requests:
            await db.commit()
        return {"checked": len(requests), "escalated": escalated}


def default_tasks() -> list[ScheduledTask]:
    return [
        FailedAgentRunFollowUpTask(),
        StalePendingApprovalReminderTask(),
        StaleRequestEscalationTask(),
    ]
