"""
Business module registry — the single place a new business gets plugged
into the platform.

To add a business: write a `BusinessModule` (see base.py) and call
`register_business_module(YourModule())`, typically as the one line at the
bottom of `app/connectors/__init__.py` (see how TolemateModule is wired in
there). Nothing else changes: `app/tools/registry.py` and
`app/agents/registry.py` both read from this registry automatically.
"""
from __future__ import annotations

from app.agents.base_agent import BaseAgent
from app.connectors.base import BusinessModule
from app.tools.base import Tool

_business_modules: list[BusinessModule] = []


def register_business_module(module: BusinessModule) -> None:
    _business_modules.append(module)
    # Allow registering a business at runtime (e.g. in a test, or a future
    # admin "activate business" flow) without restarting the process —
    # invalidate the caches that build from this list.
    from app.agents.registry import _agents as _agents_cache
    from app.tools.registry import get_tool_registry

    get_tool_registry.cache_clear()
    _agents_cache.cache_clear()


def list_business_modules() -> list[BusinessModule]:
    return list(_business_modules)


def all_business_tools() -> list[Tool]:
    tools: list[Tool] = []
    for module in _business_modules:
        tools.extend(module.get_tools())
    return tools


def all_business_agents() -> list[BaseAgent]:
    agents: list[BaseAgent] = []
    for module in _business_modules:
        agents.extend(module.get_agents())
    return agents
