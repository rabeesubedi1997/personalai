from fastapi import APIRouter

from app.api.v1 import (
    admin,
    agents,
    ai_smoke,
    approvals,
    audit,
    auth,
    billing,
    health,
    integrations,
    marketplace,
    memory,
    notifications,
    public,
    requests,
    scheduler,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(ai_smoke.router, prefix="/ai", tags=["ai"])
api_router.include_router(agents.router, tags=["agents"])
api_router.include_router(requests.router, tags=["requests"])
api_router.include_router(memory.router, tags=["memory"])
api_router.include_router(approvals.router, tags=["approvals"])
api_router.include_router(audit.router, tags=["audit"])
api_router.include_router(notifications.router, tags=["notifications"])
api_router.include_router(scheduler.router, tags=["scheduler"])
api_router.include_router(billing.router, tags=["billing"])
api_router.include_router(admin.router, tags=["admin"])
api_router.include_router(marketplace.router, tags=["marketplace"])
api_router.include_router(integrations.router, tags=["integrations"])
api_router.include_router(public.router, tags=["public"])
