"""
Public, API-key-authenticated agent chat — the endpoint an external site's
embedded chat widget calls. No PersonalOps login involved: the widget's
visitors are anonymous to this platform, attributed to one lazily-created
per-tenant "widget" system user (see app/services/widget_users.py) so the
rest of the platform (billing usage, AgentRun history, approvals,
notifications) keeps working unchanged.

CORS for this path specifically is permissive (see
PublicCorsMiddleware in app/main.py) — unlike every other endpoint in this
API, which is restricted to the dashboard's own origin, this one is
designed to be called from arbitrary third-party sites.
"""
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.agents import AgentRunResponse
from app.services.agent_execution import execute_agent_run
from app.services.api_keys import authenticate_api_key
from app.services.widget_users import get_or_create_widget_user

router = APIRouter()


class PublicChatRequest(BaseModel):
    message: str
    # The embedding site generates/stores this itself (e.g. in the
    # visitor's browser) to keep one conversation thread going across
    # messages — omit to start a new conversation.
    conversation_id: uuid.UUID | None = None


@router.post("/public/chat", response_model=AgentRunResponse)
async def public_chat(
    body: PublicChatRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> AgentRunResponse:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header."
        )
    api_key = await authenticate_api_key(db, x_api_key)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key."
        )

    widget_user = await get_or_create_widget_user(db, api_key.tenant_id)

    return await execute_agent_run(
        db,
        tenant_id=api_key.tenant_id,
        acting_user_id=widget_user.id,
        agent_slug=api_key.agent_slug,
        message=body.message,
        conversation_id=body.conversation_id,
    )
