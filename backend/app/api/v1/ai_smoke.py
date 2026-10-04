"""
Smoke-test endpoint for the AI provider — not part of the agent
orchestrator (that's Phase 2). This exists only so Phase 1 can prove the
Ollama + Qwen setup actually works end-to-end before any agent logic is
built on top of it.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.security.deps import get_current_user
from app.services.ai.base import ChatMessage, GenerationResult
from app.services.ai.factory import get_ai_provider

router = APIRouter()


class PromptRequest(BaseModel):
    prompt: str


class PromptResponse(BaseModel):
    model: str
    content: str


@router.post("/smoke-test", response_model=PromptResponse)
async def smoke_test(body: PromptRequest, _user=Depends(get_current_user)) -> PromptResponse:
    provider = get_ai_provider()
    result: GenerationResult = await provider.chat(
        [
            ChatMessage(
                role="system",
                content="You are a concise diagnostic assistant for PersonalOps AI.",
            ),
            ChatMessage(role="user", content=body.prompt),
        ]
    )
    return PromptResponse(model=result.model, content=result.content)
