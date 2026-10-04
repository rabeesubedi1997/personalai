"""
Manual scheduler trigger — runs all proactive-automation tasks once,
immediately, instead of waiting for the next tick. Useful for ops (force a
check now) and for verifying the tasks work without waiting
SCHEDULER_INTERVAL_SECONDS. Restricted to platform admins since it runs
checks across potentially sensitive operational state.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.models.user import Role, User
from app.scheduler.engine import get_scheduler
from app.security.deps import get_current_user

router = APIRouter()


@router.post("/scheduler/run")
async def run_scheduler_once(current_user: User = Depends(get_current_user)) -> dict:
    if current_user.role != Role.PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can trigger the scheduler manually.",
        )
    return await get_scheduler().run_once()
