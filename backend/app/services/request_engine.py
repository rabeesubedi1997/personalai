"""
Request lifecycle state machine (spec Section 13).

This is intentionally the ONLY place that decides whether a status
transition is legal. Nothing else — API handlers, agents, the
orchestrator — should write `request.status = X` directly; they go through
`RequestEngine.transition()` so an invalid jump (e.g. RECEIVED straight to
COMPLETED) is always caught, and every change leaves a trail in
`status_history`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.request import TERMINAL_STATUSES, Request, RequestStatus

# Forward/lateral edges for the generic lifecycle. Every non-terminal state
# can also always move to CANCELLED, FAILED, or ESCALATED (handled
# separately below) — kept out of this table to avoid repeating it 8 times.
_ALLOWED_TRANSITIONS: dict[RequestStatus, set[RequestStatus]] = {
    RequestStatus.RECEIVED: {RequestStatus.UNDERSTANDING},
    RequestStatus.UNDERSTANDING: {
        RequestStatus.NEEDS_INFORMATION,
        RequestStatus.VALIDATING,
    },
    RequestStatus.NEEDS_INFORMATION: {
        RequestStatus.UNDERSTANDING,
        RequestStatus.VALIDATING,
    },
    RequestStatus.VALIDATING: {
        RequestStatus.NEEDS_INFORMATION,
        RequestStatus.SEARCHING,
    },
    RequestStatus.SEARCHING: {
        RequestStatus.NEEDS_INFORMATION,
        RequestStatus.MATCHING,
    },
    RequestStatus.MATCHING: {
        RequestStatus.SEARCHING,
        RequestStatus.WAITING_FOR_CONFIRMATION,
    },
    RequestStatus.WAITING_FOR_CONFIRMATION: {
        RequestStatus.MATCHING,
        RequestStatus.EXECUTING,
    },
    RequestStatus.EXECUTING: {RequestStatus.VERIFYING},
    RequestStatus.VERIFYING: {
        RequestStatus.EXECUTING,
        RequestStatus.COMPLETED,
    },
}


class InvalidTransitionError(ValueError):
    pass


class RequestEngine:
    @staticmethod
    def allowed_next_statuses(current: RequestStatus) -> set[RequestStatus]:
        if current in TERMINAL_STATUSES:
            return set()
        return _ALLOWED_TRANSITIONS.get(current, set()) | {
            RequestStatus.CANCELLED,
            RequestStatus.FAILED,
            RequestStatus.ESCALATED,
        }

    @classmethod
    def transition(
        cls, request: Request, new_status: RequestStatus, *, note: str | None = None
    ) -> Request:
        current = request.status
        if new_status not in cls.allowed_next_statuses(current):
            raise InvalidTransitionError(
                f"Cannot transition request from '{current.value}' to "
                f"'{new_status.value}'."
            )

        history = list(request.status_history or [])
        history.append(
            {
                "from": current.value,
                "to": new_status.value,
                "note": note,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        request.status_history = history
        request.status = new_status
        return request
