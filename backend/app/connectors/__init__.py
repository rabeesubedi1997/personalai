"""
Business connectors (spec Section 15/19). This is the one file you touch
to activate a business module for the whole platform — everything else
(tool registry, agent registry, the `/api/v1/agents` and `/api/v1/tools`
endpoints) reads from `app.connectors.registry` automatically.

To add a new business later:
    1. Write app/connectors/<business>/{connector,tools,agent,module}.py
       following the Tolemate example below.
    2. Add one line here: `register_business_module(<Business>Module())`.
That's it — no other core file changes. See docs/CONNECTORS.md and
tests/test_business_module_extensibility.py for the proof.
"""
from app.connectors.base import BusinessModule
from app.connectors.registry import (
    all_business_agents,
    all_business_tools,
    list_business_modules,
    register_business_module,
)
from app.connectors.ghar_nepal.module import GharNepalModule
from app.connectors.tolemate.module import TolemateModule

register_business_module(TolemateModule())
register_business_module(GharNepalModule())

__all__ = [
    "BusinessModule",
    "register_business_module",
    "list_business_modules",
    "all_business_tools",
    "all_business_agents",
]
