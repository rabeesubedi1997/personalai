"""
Human Approval Engine endpoints (spec Section 12):
Approval Request -> Pending -> Approved/Rejected -> Execute if approved ->
Record result.

Approve/reject are synchronous here (no background worker yet — that's
Phase 10's proactive automation territory): approving a request runs the
tool immediately and records whatever actually happened, success or
failure. It never marks an approval "executed" without having actually run
the tool (spec Section 47: never claim success when an action failed).
"""
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.approval import Approval, ApprovalStatus
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.approvals import ApprovalDecision, ApprovalOut
from app.security.deps import get_current_user
from app.services.ai.factory import get_ai_provider
from app.tools.base import ToolContext, ToolExecutionError
from app.tools.registry import get_tool_registry

router = APIRouter()


async def _get_tenant_approval(
    approval_id: uuid.UUID, current_user: User, db: AsyncSession
) -> Approval:
    result = await db.execute(
        select(Approval).where(
            Approval.id == approval_id, Approval.tenant_id == current_user.tenant_id
        )
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    return approval


async def _audit(db: AsyncSession, *, tenant_id, event_type, actor, status_, approval, detail):
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            event_type=event_type,
            actor=actor,
            tool_name=approval.tool_name,
            agent_run_id=approval.agent_run_id,
            approval_id=approval.id,
            status=status_,
            detail=detail,
        )
    )
    await db.commit()


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    approval_status: ApprovalStatus | None = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Approval]:
    query = select(Approval).where(Approval.tenant_id == current_user.tenant_id)
    if approval_status is not None:
        query = query.where(Approval.status == approval_status)
    query = query.order_by(Approval.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/approvals/{approval_id}", response_model=ApprovalOut)
async def get_approval(
    approval_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Approval:
    return await _get_tenant_approval(approval_id, current_user, db)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalOut)
async def approve(
    approval_id: uuid.UUID,
    body: ApprovalDecision,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Approval:
    approval = await _get_tenant_approval(approval_id, current_user, db)
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval already decided (status={approval.status.value}).",
        )

    await _audit(
        db,
        tenant_id=current_user.tenant_id,
        event_type="approval_approved",
        actor=str(current_user.id),
        status_="approved",
        approval=approval,
        detail={"note": body.note},
    )

    ai_provider = get_ai_provider()
    context = ToolContext(tenant_id=current_user.tenant_id, db=db, ai_provider=ai_provider)
    registry = get_tool_registry()

    approval.decided_by_user_id = current_user.id
    approval.decision_note = body.note

    try:
        # Bypass the requires_approval re-raise this second time: we ARE
        # the approval. Execute the underlying tool directly rather than
        # going through registry.execute() (which would just raise
        # ApprovalRequiredError again).
        tool = registry.get(approval.tool_name)
        if tool is None or approval.tool_name not in approval.allowed_tool_names:
            raise ToolExecutionError(
                f"Tool '{approval.tool_name}' is no longer permitted or no longer exists."
            )
        output = await asyncio.wait_for(
            tool.execute(context, **approval.arguments), timeout=tool.timeout_seconds
        )
        approval.status = ApprovalStatus.EXECUTED
        approval.result = {"content": output.content, "data": output.data}
        await _audit(
            db,
            tenant_id=current_user.tenant_id,
            event_type="approval_executed",
            actor=str(current_user.id),
            status_="executed",
            approval=approval,
            detail={"result": approval.result},
        )
    except Exception as exc:
        approval.status = ApprovalStatus.FAILED
        approval.error = str(exc)
        await _audit(
            db,
            tenant_id=current_user.tenant_id,
            event_type="approval_execution_failed",
            actor=str(current_user.id),
            status_="failed",
            approval=approval,
            detail={"error": str(exc)},
        )

    await db.commit()
    await db.refresh(approval)
    return approval


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalOut)
async def reject(
    approval_id: uuid.UUID,
    body: ApprovalDecision,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Approval:
    approval = await _get_tenant_approval(approval_id, current_user, db)
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval already decided (status={approval.status.value}).",
        )

    approval.status = ApprovalStatus.REJECTED
    approval.decided_by_user_id = current_user.id
    approval.decision_note = body.note
    await db.commit()
    await db.refresh(approval)

    await _audit(
        db,
        tenant_id=current_user.tenant_id,
        event_type="approval_rejected",
        actor=str(current_user.id),
        status_="rejected",
        approval=approval,
        detail={"note": body.note},
    )
    return approval
