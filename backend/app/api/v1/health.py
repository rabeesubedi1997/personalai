from fastapi import APIRouter
from sqlalchemy import text

from app.core.redis_client import ping as redis_ping
from app.db.session import engine
from app.schemas.health import HealthStatus
from app.services.ai.factory import get_ai_provider

router = APIRouter()


@router.get("/health", response_model=HealthStatus)
async def health() -> HealthStatus:
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "unavailable"

    redis_status = "ok" if await redis_ping() else "unavailable"

    ai_status = "ok" if await get_ai_provider().health_check() else "unavailable"

    overall = "ok" if db_status == "ok" else "degraded"
    return HealthStatus(
        status=overall, database=db_status, redis=redis_status, ai_provider=ai_status
    )
