"""
Code-driven conversation flows.

Some jobs must not depend on a small language model deciding to do the right
thing. Booking is the clear case: told the customer's service, date, name and
email, the 3B model kept chatting ("please provide your name…") instead of
calling the booking tool, then sometimes claimed a booking that never existed.

A `ConversationFlow` takes over such a conversation. The model is used only to
READ what the customer said (structured extraction); everything that matters —
which detail is still missing, availability checks, the booking itself, and the
wording of the reply — is plain code. Whatever a flow does, it does through the
normal tool registry, so permissions, timeouts and the audit trail still apply.

A flow may return None to decline a message (e.g. "what's your cancellation
policy?"), and the agent's normal model-driven loop handles it instead.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.services.ai.base import AIProvider, ChatMessage


@dataclass
class FlowToolResult:
    content: str
    data: dict[str, Any] | None
    is_error: bool


# (tool_name, arguments) -> result. Provided by the orchestrator: it runs the
# tool through the registry and records it in the run's trace and transcript.
RunTool = Callable[[str, dict[str, Any]], Awaitable[FlowToolResult]]


@dataclass
class FlowOutcome:
    reply: str
    # Free-form note for logs/tests about which branch of the flow answered.
    step: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


class ConversationFlow(ABC):
    @abstractmethod
    async def handle(
        self,
        *,
        user_message: str,
        history: list[ChatMessage],
        ai_provider: AIProvider,
        run_tool: RunTool,
    ) -> FlowOutcome | None:
        """Answer this message, or return None to hand it to the agent."""
