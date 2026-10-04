from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogOut
from app.security.deps import get_current_user

router = APIRouter()


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    event_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLog]:
    """Spec Section 25: must be able to answer 'what did the agent do, why,
    which tool, what result, who approved it' — this is that query
    surface. Tenant-scoped like everything else."""
    query = select(AuditLog).where(AuditLog.tenant_id == current_user.tenant_id)
    if event_type is not None:
        query = query.where(AuditLog.event_type == event_type)
    query = query.order_by(AuditLog.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())
