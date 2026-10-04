# Tools

No tool registry exists yet — this is Phase 2 scope.

## Design (will be implemented in Phase 2)
Each tool will define: name, description, input schema, output schema,
permission level, agent access, tenant access, approval requirement,
timeout, retry policy — matching `ToolSpec` already defined in
`backend/app/services/ai/base.py` (used today only to prove Qwen2.5's
tool-calling works; the registry/execution layer around it doesn't exist
yet).

Permission levels (spec Section 11), to be enforced starting Phase 5:
- `READ` — e.g. search properties/providers/customers
- `SAFE_WRITE` — e.g. create enquiry, create internal task
- `SENSITIVE` — e.g. change booking, send customer communication
- `CRITICAL` — e.g. refund, delete production data (requires human approval)

The LLM will never get unrestricted SQL, shell, filesystem, or direct
production database access — only named, schema-validated tools.
