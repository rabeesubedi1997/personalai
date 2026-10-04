from fastapi import APIRouter

from app.api.v1 import agents, ai_smoke, auth, health, memory, requests

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(ai_smoke.router, prefix="/ai", tags=["ai"])
api_router.include_router(agents.router, tags=["agents"])
api_router.include_router(requests.router, tags=["requests"])
api_router.include_router(memory.router, tags=["memory"])
