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

Two flavours of the same chat: `/public/chat` returns the whole reply when
it's finished; `/public/chat/stream` sends it as Server-Sent Events so the
visitor sees words appear within seconds instead of staring at a spinner for
the full generation time.
"""
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.api_key import AgentApiKey
from app.schemas.agents import AgentRunResponse
from app.services.agent_execution import execute_agent_run, prepare_agent_run, stream_agent_run
from app.services.api_keys import authenticate_api_key
from app.services.widget_users import get_or_create_widget_user

router = APIRouter()


class PublicChatRequest(BaseModel):
    message: str
    # The embedding site generates/stores this itself (e.g. in the
    # visitor's browser) to keep one conversation thread going across
    # messages — omit to start a new conversation.
    conversation_id: uuid.UUID | None = None


async def _authenticate(db: AsyncSession, x_api_key: str | None) -> AgentApiKey:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header."
        )
    api_key = await authenticate_api_key(db, x_api_key)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key."
        )
    return api_key


@router.post("/public/chat", response_model=AgentRunResponse)
async def public_chat(
    body: PublicChatRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> AgentRunResponse:
    api_key = await _authenticate(db, x_api_key)
    widget_user = await get_or_create_widget_user(db, api_key.tenant_id)

    return await execute_agent_run(
        db,
        tenant_id=api_key.tenant_id,
        acting_user_id=widget_user.id,
        agent_slug=api_key.agent_slug,
        message=body.message,
        conversation_id=body.conversation_id,
    )


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/public/chat/stream")
async def public_chat_stream(
    body: PublicChatRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Server-Sent Events. Events (one JSON object per `data:` line):
        {"type":"start","conversation_id":...}  sent immediately
        {"type":"token","text":...}              reply text as it's generated
        {"type":"tool","text":<tool name>}       the agent is running a tool
        {"type":"done","data":{...}}             final AgentRunResponse
        {"type":"error","text":...}              the run failed
    Auth, install and quota checks run BEFORE streaming starts, so those
    failures are ordinary HTTP errors (401/404/402), not a broken stream."""
    api_key = await _authenticate(db, x_api_key)
    widget_user = await get_or_create_widget_user(db, api_key.tenant_id)
    prepared = await prepare_agent_run(
        db,
        tenant_id=api_key.tenant_id,
        acting_user_id=widget_user.id,
        agent_slug=api_key.agent_slug,
        message=body.message,
        conversation_id=body.conversation_id,
    )

    async def events() -> AsyncIterator[str]:
        yield _sse({"type": "start", "conversation_id": str(prepared.conversation_id)})
        async for event in stream_agent_run(prepared):
            yield _sse(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Stops nginx-style reverse proxies from buffering the stream
            # until it ends, which would defeat the point.
            "X-Accel-Buffering": "no",
        },
    )
