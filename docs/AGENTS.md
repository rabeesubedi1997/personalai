# Agents

## Implemented (Phase 2)
`BaseAgent` (`backend/app/agents/base_agent.py`) declares `name`,
`description`, `system_prompt`, and an explicit `allowed_tools` list —
agents never get unrestricted tool access.

**General Assistant Agent** (`general_assistant.py`) is the one demonstration
agent: receives a message, the orchestrator lets it select from its 3
allowed mock tools (`get_current_time`, `search_knowledge_base`,
`create_task`), executes, returns a result. Registered in
`agents/registry.py`; run via `POST /api/v1/agents/run`.

Every run is bounded by `AGENT_MAX_ITERATIONS` / `AGENT_MAX_TOOL_CALLS` /
per-tool `timeout_seconds` (`app/core/config.py` + `app/tools/base.py`) —
verified by tests that force a provider to request tool calls forever and
confirm the orchestrator stops rather than looping (`tests/test_orchestrator.py`).

### Verified finding: tool-use must be explicitly mandated in the prompt
Live-tested against Qwen2.5 3B: with a softer system prompt
("use tools when needed"), the model answered a factual question
("What are your support hours?") **from invented memory** instead of
calling `search_knowledge_base` — a direct violation of spec Section 47/48
("never invent business data"). Rewriting the prompt to explicitly mandate
tool calls for business-fact questions (see `general_assistant.py`) fixed
this; re-verified live that the model now calls the tool and, for a query
with no matching document, honestly reports the information is unavailable
rather than fabricating an answer. This is recorded as a standing
constraint on every future agent's system prompt, not a one-off prompt
tweak: **small local models need explicit, mandatory tool-use instructions
per fact category — "use tools when appropriate" is not reliable enough.**

## Planned (Phase 3+)
```
backend/app/agents/
├── base_agent.py          ✅
├── general_assistant.py   ✅ (Phase 2 demo)
├── customer_support_agent.py
├── sales_agent.py
├── property_agent.py
├── service_booking_agent.py
└── ...
```
Permissions, escalation rules, and required-data declarations beyond
`allowed_tools` are added as real business agents are built (Phase 6+).
