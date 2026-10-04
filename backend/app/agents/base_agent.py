"""
Agent base class (spec Section 9). Every agent declares its identity,
system prompt, and — critically — an explicit `allowed_tools` list. There
is no "give this agent every tool" shortcut; an agent that needs a new
capability gets it added to its own allow-list, deliberately.
"""
from __future__ import annotations

from abc import ABC


class BaseAgent(ABC):
    name: str
    description: str
    system_prompt: str
    allowed_tools: list[str] = []
    # Phase 12 (Agent Marketplace): catalog metadata. Bump `version` when an
    # agent's behavior changes meaningfully (prompt, tool list) — installed
    # tenants keep running their installed version's metadata until they
    # reinstall, same convention as any package marketplace.
    version: str = "1.0.0"
    category: str = "general"
