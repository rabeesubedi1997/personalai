import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.public_cors import PublicCorsMiddleware
from app.db.base import Base
from app.db.session import async_session_factory, engine
from app.scheduler.engine import get_scheduler
from app.services.ai import cache_warmer
from app.services.ai.factory import get_ai_provider
from app.services.billing import seed_default_plans
from app.tools.registry import get_tool_registry

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1: auto-create tables for the dev SQLite DB so the app boots
    # with zero manual steps. Once Alembic migrations are the source of
    # truth (see backend/alembic), this is restricted to app_env=="test".
    if settings.app_env in ("development", "test"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as db:
        await seed_default_plans(db)

    scheduler_task: asyncio.Task | None = None
    if settings.scheduler_enabled:
        scheduler = get_scheduler()
        scheduler_task = asyncio.create_task(
            scheduler.run_forever(settings.scheduler_interval_seconds)
        )

    warmer_task: asyncio.Task | None = None
    if settings.cache_warmer_enabled and settings.ai_provider == "ollama":
        warmer_task = asyncio.create_task(
            cache_warmer.run_forever(
                get_ai_provider(), get_tool_registry(), settings.cache_warmer_interval_seconds
            )
        )

    logger.info(
        "app_startup",
        app_env=settings.app_env,
        ai_provider=settings.ai_provider,
        scheduler_enabled=settings.scheduler_enabled,
        cache_warmer_enabled=settings.cache_warmer_enabled,
    )
    yield

    if scheduler_task is not None:
        get_scheduler().stop()
        await scheduler_task
    if warmer_task is not None:
        warmer_task.cancel()
        with suppress(asyncio.CancelledError):
            await warmer_task
    logger.info("app_shutdown")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Added after the dashboard-restricted CORSMiddleware above so it wraps
# outermost (Starlette applies middleware in reverse of add order) — see
# app/core/public_cors.py for why /api/v1/public/* needs a different policy.
app.add_middleware(PublicCorsMiddleware)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "running"}
