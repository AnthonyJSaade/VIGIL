# Vigil — Build Context

> This file tracks the current state of the build so any new chat session can pick up where we left off.
> Updated after each significant change.

## Last Updated
2026-04-08

## Current Phase
**Phase 1 complete** — Data models, SQLite schema, and CRUD helpers are built. Ready for Phase 2 (Scanner Runner).

## What Exists

| File | Purpose |
|---|---|
| `AGENTS.md` | Project charter: mission, MVP flow, scope boundaries, build order, agent behavior rules |
| `PLAN.md` | Full implementation plan: architecture diagrams, directory structure, all 10 phases, tech decisions |
| `CONTEXT.md` | This file — cross-session build context |
| `.gitignore` | Python, Node, Docker, IDE exclusions |
| `.cursor/rules/workflow.mdc` | Start in plan mode for multi-file changes, verify after edits, respect demo scope |
| `.cursor/rules/architecture.mdc` | Deterministic core, LLMs only for explain/patch/critique, explicit schemas |
| `.cursor/rules/safety.mdc` | Never "fix" vulns by suppressing rules, removing auth, or widening trust |
| `backend/requirements.txt` | Python dependencies: fastapi, uvicorn, anthropic, aiosqlite, pydantic, pydantic-settings, jinja2, python-multipart |
| `backend/app/main.py` | FastAPI app with CORS middleware and lifespan (calls init_db on startup) |
| `backend/app/config.py` | Settings via pydantic-settings (VIGIL_ env prefix): anthropic_api_key, db_path, demo_repos_path |
| `backend/app/models/finding.py` | `Finding` + `SeverityLevel` enum |
| `backend/app/models/patch.py` | `PatchProposal` (supports attempt number + prior_concerns for retry) |
| `backend/app/models/critic.py` | `CriticVerdict` |
| `backend/app/models/verification.py` | `VerificationReport` |
| `backend/app/models/trace.py` | `TraceEvent` + `AgentRole` + `TraceAction` enums |
| `backend/app/models/run.py` | `Run` + `RunStatus` enum |
| `backend/app/models/__init__.py` | Re-exports all models and enums |
| `backend/app/db.py` | SQLite schema (6 tables) + async CRUD helpers + smoke test |

## What Does NOT Exist Yet
- No API routes (Phase 3-4)
- No scanner runner (Phase 2)
- No LLM agents (Phase 5-6)
- No verification pipeline (Phase 7)
- No export bundle (Phase 8)
- No frontend code (Phase 9)
- No demo repo (Phase 10)
- No Docker setup (Phase 10)

## Tech Stack Decisions (Locked)

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI |
| Frontend | Next.js (App Router) + Tailwind CSS |
| Scanner | Semgrep CLI (deterministic, no LLM) |
| LLM | Anthropic Claude (via `anthropic` Python SDK) |
| Database | SQLite via aiosqlite |
| Streaming | Server-Sent Events (SSE) via asyncio.Queue |
| Export | Self-contained HTML report (Jinja2) + ZIP fallback |
| Containerization | Docker + Docker Compose |

## Three Agent Roles

| Role | Type | What It Does |
|---|---|---|
| **Hunter** | Deterministic | Runs Semgrep, normalizes findings into typed schema |
| **Surgeon** | LLM (Claude) | Generates minimal patch for a single finding, supports retry with Critic feedback |
| **Critic** | LLM (Claude) | Independently reviews patch, approves or rejects with concerns list |

## Key Architecture Rules
- Deterministic spine first, LLM features second
- Every scanner output normalizes to `Finding` schema
- Every patch targets a single finding
- Critic has no access to Surgeon's reasoning (independent)
- Verification runs on a sandbox copy, never the original
- Surgeon-Critic feedback loop: max 2 attempts
- All agent steps publish SSE events for live UI streaming
- Trace events stored for full Hunter -> Surgeon -> Critic -> Verifier history

## Data Models (Implemented)
- `Finding` — id, run_id, scanner, rule_id, severity (error/warning/info), message, file_path, start_line, end_line, snippet, metadata, created_at
- `PatchProposal` — id, finding_id, diff, explanation, model_used, attempt (1 or 2), prior_concerns (list or None), created_at
- `CriticVerdict` — id, patch_id, approved (bool), reasoning, concerns (list), model_used, created_at
- `VerificationReport` — id, patch_id, scanner_rerun_clean (bool), tests_passed (bool or None), details, created_at
- `TraceEvent` — id, run_id, role (hunter/surgeon/critic/verifier), action (enum of 10 values), payload (dict), timestamp
- `Run` — id, repo_id, status (pending/scanning/completed/failed), finding_count, created_at

## SQLite Tables (Implemented)
- `runs`, `findings`, `patches`, `verdicts`, `verifications`, `trace_events`
- All have async CRUD helpers in `backend/app/db.py`

## API Endpoints (To Be Implemented)
- `GET /api/repos` — list curated demo repos
- `POST /api/runs` — start audit run
- `GET /api/runs/{id}` — run metadata
- `GET /api/runs/{id}/stream` — SSE event stream
- `GET /api/runs/{id}/findings` — findings list
- `GET /api/findings/{id}` — finding detail
- `POST /api/findings/{id}/patch` — trigger Surgeon-Critic loop
- `POST /api/patches/{id}/verify` — sandbox verification
- `GET /api/runs/{id}/export` — HTML report or ZIP bundle

## Build Order
1. Contracts and data models
2. Scanner runner + findings normalization
3. Run API + SSE streaming
4. Findings explorer backend
5. Patch proposal pipeline (Surgeon)
6. Critic review + feedback loop
7. Verification pipeline
8. Export bundle (HTML report)
9. UI (Next.js)
10. Demo repo + Docker

## Team
- 2-person team

## Repository
- GitHub: https://github.com/AnthonyJSaade/VIGIL
- Branch: `main`

## Session Log

| Date | What Happened |
|---|---|
| 2026-04-08 | Created AGENTS.md, PLAN.md, .gitignore, cursor rules. Initialized git repo. Pushed to GitHub. Plan finalized with 5 upgrades: feedback loop, SSE streaming, vibe-coded demo repo, agent personas, HTML export. |
| 2026-04-08 | Phase 1 complete: backend skeleton, 6 Pydantic models with enums, SQLite schema (6 tables), async CRUD helpers, FastAPI lifespan wiring. All verified. |
