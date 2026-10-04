# Tools

## Implemented (Phase 2)
`Tool` base class (`backend/app/tools/base.py`): `name`, `description`,
JSON-schema `parameters`, `permission_level`, `requires_approval`,
`timeout_seconds`, async `execute()`.

`ToolRegistry` (`tools/registry.py`) is the only place a tool name resolves
to executable code:
- `specs_for(allowed_tool_names)` — hands the model only the tool specs an
  agent is allowed to use, never the full registry.
- `execute(name, arguments, allowed_tool_names=...)` — **hard-refuses**
  (raises `ToolExecutionError`, does not execute) a tool that either
  doesn't exist or isn't in the calling agent's own allow-list, and enforces
  each tool's `timeout_seconds` via `asyncio.wait_for`. Covered by
  `tests/test_tool_registry.py` and `tests/test_orchestrator.py`
  (`test_unauthorized_tool_call_is_denied_not_executed`).

Permission levels (spec Section 11) are modeled now as `PermissionLevel`
(`READ` / `SAFE_WRITE` / `SENSITIVE` / `CRITICAL`); **enforcement beyond
the agent allow-list** (e.g. requiring human approval before a `CRITICAL`
tool runs) is Phase 5.

## Mock tools (Phase 2, `tools/mock_tools.py`)
- `get_current_time` (READ)
- `search_knowledge_base` (READ) — stands in for the Phase 4 pgvector
  knowledge base; same name/shape, real implementation later
- `create_task` (SAFE_WRITE)

These are explicitly mocks (spec: "Use mock tools initially") — swapped for
real connector-backed tools starting Phase 6.

The LLM never gets unrestricted SQL, shell, filesystem, or direct
production database access — only named, schema-validated tools, resolved
through the registry above.
