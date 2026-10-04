"""SchedulerEngine: a plain asyncio loop running the registered
ScheduledTasks on a fixed interval. Started/stopped from app.main's
lifespan. Deliberately simple — see base.py for why no external
scheduling library is used."""
from __future__ import annotations

import asyncio
from functools import lru_cache

from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.scheduler.base import ScheduledTask
from app.scheduler.tasks import default_tasks

logger = get_logger(__name__)


class SchedulerEngine:
    def __init__(self, tasks: list[ScheduledTask]) -> None:
        self.tasks = tasks
        self._stop_event = asyncio.Event()

    async def run_once(self) -> dict:
        results: dict[str, dict] = {}
        async with async_session_factory() as db:
            for task in self.tasks:
                try:
                    results[task.name] = await task.run(db)
                except Exception as exc:  # a buggy task must not kill the loop
                    logger.error("scheduler_task_failed", task=task.name, error=str(exc))
                    results[task.name] = {"error": str(exc)}
        return results

    async def run_forever(self, interval_seconds: float) -> None:
        logger.info("scheduler_started", interval_seconds=interval_seconds)
        while not self._stop_event.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                pass
        logger.info("scheduler_stopped")

    def stop(self) -> None:
        self._stop_event.set()


@lru_cache
def get_scheduler() -> SchedulerEngine:
    return SchedulerEngine(default_tasks())
