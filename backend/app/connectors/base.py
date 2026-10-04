"""
The pluggable unit for adding a new business to the platform (spec
Section 15/19: "adding a new business should not require rewriting the
core platform").

A `BusinessModule` is everything one business integration contributes:
its tools and its agent(s). Nothing else in the core — the tool registry,
the agent registry, the orchestrator, the Request engine, the approval
engine — needs to know a given business exists. Register the module once
(see app/connectors/registry.py) and the core picks it up automatically.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.agents.base_agent import BaseAgent
from app.tools.base import Tool


class BusinessModule(ABC):
    name: str
    description: str

    @abstractmethod
    def get_tools(self) -> list[Tool]:
        """Tools this business contributes to the platform's tool
        registry. Each tool declares its own permission_level — nothing
        business-specific is assumed about risk level."""

    @abstractmethod
    def get_agents(self) -> list[BaseAgent]:
        """Specialist agent(s) for this business, with an explicit
        allowed_tools list (spec Section 9) drawn from get_tools() above
        plus whatever core tools (e.g. cancel_booking, create_task) make
        sense for this business."""
