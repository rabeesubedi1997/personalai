from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.base import Base
from app.db.session import engine

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
    logger.info("app_startup", app_env=settings.app_env, ai_provider=settings.ai_provider)
    yield
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

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "running"}
