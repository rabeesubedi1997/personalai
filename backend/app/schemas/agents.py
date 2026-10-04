import uuid

from pydantic import BaseModel

from app.models.agent_run import AgentRunStatus


class AgentRunRequest(BaseModel):
    agent: str
    message: str
    # Omit to start a new conversation; pass back the conversation_id from
    # a prior response to continue it (e.g. "yes, book it" as a follow-up).
    conversation_id: uuid.UUID | None = None


class ToolTraceEntry(BaseModel):
    tool: str
    arguments: dict
    result: str
    is_error: bool


class AgentRunResponse(BaseModel):
    run_id: uuid.UUID
    agent: str
    status: AgentRunStatus
    final_response: str
    iterations: int
    tool_trace: list[ToolTraceEntry]
    model: str
    error: str | None = None
    # Set only when status == awaiting_approval.
    approval_id: uuid.UUID | None = None
    # Always set — pass this back as conversation_id to continue the thread.
    conversation_id: uuid.UUID | None = None


class AgentInfo(BaseModel):
    name: str
    description: str
    allowed_tools: list[str]


class ToolInfo(BaseModel):
    name: str
    description: str
    permission_level: str
    requires_approval: bool
