"""
Proactive automation (spec Section 21):

    Scheduler -> Trigger -> Agent -> Workflow -> Tool -> Verification -> Notification

Phase 10 implements the generic, business-agnostic slice of this: a
lightweight in-process scheduler that periodically checks for things no
one is actively watching — a stale pending approval, a failed agent run,
a request that hasn't moved — and raises them via the Phase 9 notification
system or the Phase 5 audit log. It deliberately does NOT invoke the full
agent orchestrator on a timer (that's a larger, business-specific concern
better built once a real scheduled workflow is needed); this is the
monitoring/escalation half of Section 21, not proactive agent execution.

No external scheduling library (e.g. APScheduler) is introduced — per the
master spec's "don't introduce a complex framework unless required," a
plain asyncio loop is enough for periodic, idempotent, tenant-agnostic
checks like these.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession


class ScheduledTask(ABC):
    name: str

    @abstractmethod
    async def run(self, db: AsyncSession) -> dict:
        """Run one check across all tenants. Must be idempotent — safe to
        run again next tick without duplicating notifications/side effects
        (each task tracks its own 'already handled' flag). Returns a small
        summary dict for observability, e.g. {"checked": 3, "notified": 1}."""
