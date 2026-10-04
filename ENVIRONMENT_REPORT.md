# Environment Report — PersonalOps AI

Generated: 2026-10-04
Scope: Phase 0 — Environment Discovery (read-only; no system changes made)

---

## 1. Hardware

| Component | Detail |
|---|---|
| Machine | MSI MS-7D82, motherboard MSI PRO H410M-B |
| CPU | Intel Core i5-10500 @ 3.10GHz — 6 physical cores / 12 logical processors |
| RAM (installed) | 15.8 GB usable |
| RAM (free right now) | **~1.7 GB free**, 7.8 GB free commit — machine is under memory pressure from currently-running apps (Chrome, VS Code, Code helpers) |
| GPU | Intel UHD Graphics 630 (integrated, 1 GB shared VRAM reported) — **no dedicated/discrete GPU**. `nvidia-smi` not present. |
| Disk C: | NVMe SSD, 341 GB total, **42 GB free** |
| Disk D: | Same physical NVMe, 135 GB total, **~5 GB free** — too tight to use for Docker/model storage |
| Virtualization | Enabled in firmware (`VirtualizationFirmwareEnabled = True`), but `HypervisorPresent = False` — Hyper-V is **not currently active** on this machine |

**Conclusion:** No GPU acceleration available → all local AI inference must run **CPU-only**. This confirms the spec's requirement to design for CPU-first operation and small models only.

---

## 2. Software Installed

| Tool | Status | Version / Path |
|---|---|---|
| Python | ✅ Installed | 3.11.4 — `C:\Python311\python.exe` (also via `py -3.11`) |
| pip | ✅ Installed | 23.1.2 |
| uv / poetry | ❌ Not installed | — |
| Git | ✅ Installed | 2.40.1.windows.1 |
| Node.js | ✅ Installed | v24.18.1 — `C:\Program Files\nodejs\` (on PATH) |
| npm | ✅ Installed | 9.8.1 |
| pnpm | ❌ Not installed | — |
| Docker / Docker Compose | ❌ Not installed | — |
| WSL2 | ❌ Not installed (`wsl.exe` reports "not installed") | — |
| PostgreSQL (`psql`) | ❌ Not installed natively | — |
| Redis (`redis-server`) | ❌ Not installed natively | — |
| Ollama | ✅ Installed, daemon **not running** | v0.5.7 — `C:\Users\Admin\AppData\Local\Programs\Ollama\ollama.exe` |
| VS Code | ✅ Installed | 1.138.0 |

### Existing Ollama model found
A model is already pulled locally:
- `deepseek-r1:1.5b` (reasoning-tuned, 1.5B class) — present under `~\.ollama\models\manifests\registry.ollama.ai\library\deepseek-r1\1.5b`

This is **not** a strong tool-calling/structured-output model (DeepSeek-R1 distill models are reasoning/chain-of-thought focused and have inconsistent native tool-calling support in Ollama). It can be used for early smoke-testing, but it is not the recommended default for the agent/tool-calling workload — see recommendation below.

---

## 3. Ports

All ports the stack will need are currently free:

| Port | Use | Status |
|---|---|---|
| 8000 | FastAPI backend | free |
| 3000 | React/Next.js frontend | free |
| 5432 | PostgreSQL | free |
| 6379 | Redis | free |
| 11434 | Ollama API | free |
| 5050 | (reserved, e.g. pgAdmin) | free |
| 8080 | (reserved) | free |

No conflicting services currently running (no Postgres/Redis/Docker Windows services registered).

---

## 4. Missing Dependencies

| Missing | Needed for | Recommendation |
|---|---|---|
| Docker Desktop + WSL2 | Containerized Postgres/Redis/backend/frontend per spec Section 34 | **Optional for Phase 1.** See "Docker vs. native" decision below — low free RAM and low D: disk space make Docker Desktop (which needs a WSL2 VM with its own memory overhead, typically 2–4 GB) a real risk on this machine right now. |
| PostgreSQL | Primary datastore (Section 27) | Install **native Windows PostgreSQL 16** (with pgvector extension) instead of via Docker, to avoid WSL2/Docker memory overhead. |
| Redis | Caching/queues (Section 28) | Install native **Redis for Windows** (via Memurai or redis-windows unofficial build) or run inside a lightweight WSL2 Ubuntu instance — decide in Phase 1 depending on measured memory headroom. |
| pgvector extension | Vector memory (Section 14/27) | Install alongside native PostgreSQL. |
| uv/poetry | Python dependency management | Recommend `uv` (fast, low overhead) — will install in Phase 1 setup, not now. |

---

## 5. Recommended Local AI Model

Per spec Section 4 (detect resources → pick smallest practical model with reliable tool calling):

- **Primary recommendation:** `qwen2.5:3b-instruct` (or current Qwen3 4B-class equivalent if/when pulled) via Ollama — small, explicitly supports Ollama's native tool-calling/function-calling and structured JSON output, and fits comfortably in the ~8–10 GB of RAM this machine can spare for a model process once other apps are closed.
- **Fallback (lower resource):** `qwen2.5:1.5b-instruct` — if the 3B model proves too slow/heavy once Postgres/Redis/FastAPI are also running.
- **Already present, but not recommended as the default:** `deepseek-r1:1.5b` — kept available for experimentation, but its tool-calling behavior is unreliable, so it should not be the orchestrator's default model.
- Do **not** pull 7B+ models on this machine without closing most other applications first, and do not run two models loaded simultaneously.

This stays fully configurable via `OLLAMA_MODEL` env var — nothing is hard-coded.

---

## 6. Resource Risks

1. **Free RAM is critically low right now (~1.7 GB)** because Chrome and multiple VS Code/Code-helper processes are already consuming ~10+ GB combined. Before running Ollama + Postgres + Redis + FastAPI + a browser simultaneously, close unneeded Chrome tabs/VS Code windows, or expect swapping/slowdowns. This is a *current session* condition, not a hardware limitation — the 15.8 GB total is workable for the target stack if apps are trimmed.
2. **D: drive has only ~5 GB free.** Do not place Docker images, Ollama models, or Postgres data directories there. Default all installs/data to C: (which has 42 GB free) and monitor headroom as model files (1.5–4 GB each) and Postgres data accumulate.
3. **No discrete GPU** — confirms CPU-only inference. Expect noticeably slower token generation than a GPU box; design agent loops with generous but bounded timeouts (spec Section 8/32) to tolerate this, not to work around it indefinitely.
4. **No WSL2/Hyper-V active** — Docker Desktop will prompt to enable WSL2 on first run, which itself consumes additional RAM for the WSL2 VM (typically 2–4 GB, configurable via `.wslconfig`). Given point 1, **native-Windows services for Postgres/Redis are recommended over Docker for Phase 1**, with Docker Compose definitions still written (per spec Section 34, "if Docker Desktop causes excessive resource consumption, document an alternative local setup") for later use on a Linux server deployment.
5. **Ollama daemon is not currently running** — will need to be started (`ollama serve`) before Phase 2 AI integration work; this is a normal manual step, not an issue.

---

## 7. Recommended Configuration (for `.env.example`, Phase 1)

```
APP_ENV=development

DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/personalops
REDIS_URL=redis://localhost:6379/0

AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b-instruct

JWT_SECRET=change-me-in-dev
```

---

## 8. Phase 0 Decision Log

| Decision | Reason | Alternative | Why chosen |
|---|---|---|---|
| Native Windows Postgres/Redis instead of Docker for local dev | Free RAM is currently ~1.7 GB; WSL2+Docker VM overhead is a real risk | Docker Compose for everything | Native services use less RAM; Compose files still authored for Linux/production parity |
| Qwen2.5 3B-instruct as default model | Smallest model with reliable Ollama tool-calling + structured output | Keep deepseek-r1:1.5b as default | R1 models are reasoning-trace models with weaker/inconsistent tool-calling support |
| Project root at `~/personalops-ai`, git initialized | Matches spec Section 45 suggested structure | — | — |

---

## 9. Status: Environment Suitable for Phase 1?

**Yes, with caveats:**
- ✅ Python, Git, Node/npm, Ollama present
- ✅ All required ports free
- ✅ Sufficient disk on C:
- ⚠️ Need to install: native PostgreSQL (+pgvector), native Redis (or defer Redis to a later sub-phase and use in-process/SQL-backed state initially), and decide Docker now vs. later
- ⚠️ Need to free up RAM before running the full stack concurrently
- ⚠️ Need to pull a tool-calling-capable model (`qwen2.5:3b-instruct`) via Ollama

No destructive or heavy installs have been performed. Awaiting confirmation before proceeding to Phase 1 (project scaffolding + dependency installation).
