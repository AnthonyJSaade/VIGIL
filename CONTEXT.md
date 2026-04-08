# Vigil — Build Context

> This file tracks the current state of the build so any new chat session can pick up where we left off.
> Updated after each significant change.

## Last Updated
2026-04-08

## Current Phase
**Phase 3 complete + Hunter expansion** — Run API, SSE event bus, streaming endpoint, and hybrid scan pipeline (Semgrep + LLM review) are built. Ready for Phase 4 (Findings Explorer).

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
| `backend/app/models/finding.py` | `Finding` (with `confidence` field) + `SeverityLevel` enum |
| `backend/app/models/patch.py` | `PatchProposal` (supports attempt number + prior_concerns for retry) |
| `backend/app/models/critic.py` | `CriticVerdict` |
| `backend/app/models/verification.py` | `VerificationReport` |
| `backend/app/models/trace.py` | `TraceEvent` + `AgentRole` + `TraceAction` enums (includes LLM_REVIEW_STARTED/COMPLETED) |
| `backend/app/models/run.py` | `Run` + `RunStatus` enum |
| `backend/app/models/__init__.py` | Re-exports all models and enums |
| `backend/app/db.py` | SQLite schema (6 tables) + async CRUD helpers + smoke test |
| `backend/app/scanner/runner.py` | `run_semgrep(repo_path) -> dict` — async Semgrep CLI wrapper with timeout and error handling |
| `backend/app/scanner/normalizer.py` | `normalize_findings(raw, run_id) -> list[Finding]` — maps Semgrep JSON to Finding schema. Handles severity mapping (CRITICAL/ERROR->error, WARNING/MEDIUM->warning, INFO/LOW->info). Includes inline smoke test. |
| `backend/app/scanner/llm_reviewer.py` | `review_code(repo_path, run_id, existing_findings) -> list[Finding]` — Claude-powered code review. Collects source files, builds prompt with existing findings to skip, parses structured JSON response. Findings tagged `scanner="claude-review"` with self-assessed confidence. Graceful failure (returns empty list). |
| `backend/app/scanner/orchestrator.py` | `run_full_scan(run_id, repo_path) -> list[Finding]` — two-phase Hunter pipeline. Phase 1: Semgrep. Phase 2: LLM review. Deduplicates overlapping findings (3-line tolerance). Publishes SSE events throughout. Persists all findings. |
| `backend/app/streaming/sse.py` | `EventBus` class — in-memory publish/subscribe per run_id. Publishes to all SSE subscribers + persists as TraceEvent. Singleton `bus` instance. |
| `backend/app/routes/repos.py` | `GET /api/repos` — returns hardcoded curated demo repo list |
| `backend/app/routes/runs.py` | `POST /api/runs` — creates run, launches Hunter as background task. `GET /api/runs/{id}` — returns run metadata. Background task: calls `run_full_scan()` orchestrator (Semgrep + LLM review). |
| `backend/app/routes/stream.py` | `GET /api/runs/{id}/stream` — SSE endpoint via StreamingResponse |

## What Does NOT Exist Yet
- No findings detail endpoints (Phase 4)
- No Surgeon LLM agent (Phase 5)
- No Critic LLM agent (Phase 6)
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
| Scanner | Semgrep CLI (deterministic) + Claude LLM review (hybrid pipeline) |
| LLM | Anthropic Claude (via `anthropic` Python SDK) |
| Database | SQLite via aiosqlite |
| Streaming | Server-Sent Events (SSE) via asyncio.Queue |
| Export | Self-contained HTML report (Jinja2) + ZIP fallback |
| Containerization | Docker + Docker Compose |

## Three Agent Roles

| Role | Type | What It Does |
|---|---|---|
| **Hunter** | Hybrid (deterministic + LLM) | Phase 1: Semgrep scan. Phase 2: Claude code review. Deduplicates overlapping findings. |
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
- `Finding` — id, run_id, scanner, rule_id, severity (error/warning/info), message, file_path, start_line, end_line, snippet, confidence (float, default 1.0), metadata, created_at
- `PatchProposal` — id, finding_id, diff, explanation, model_used, attempt (1 or 2), prior_concerns (list or None), created_at
- `CriticVerdict` — id, patch_id, approved (bool), reasoning, concerns (list), model_used, created_at
- `VerificationReport` — id, patch_id, scanner_rerun_clean (bool), tests_passed (bool or None), details, created_at
- `TraceEvent` — id, run_id, role (hunter/surgeon/critic/verifier), action (enum of 12 values incl. llm_review_started/completed), payload (dict), timestamp
- `Run` — id, repo_id, status (pending/scanning/completed/failed), finding_count, created_at

## SQLite Tables (Implemented)
- `runs`, `findings`, `patches`, `verdicts`, `verifications`, `trace_events`
- All have async CRUD helpers in `backend/app/db.py`

## API Endpoints

Implemented:
- `GET /api/repos` — list curated demo repos
- `POST /api/runs` — start audit run (launches bg scan)
- `GET /api/runs/{id}` — run metadata + status
- `GET /api/runs/{id}/stream` — SSE event stream (text/event-stream)

To be implemented:
- `GET /api/runs/{id}/findings` — findings list (Phase 4)
- `GET /api/findings/{id}` — finding detail (Phase 4)
- `POST /api/findings/{id}/patch` — trigger Surgeon-Critic loop (Phase 5-6)
- `POST /api/patches/{id}/verify` — sandbox verification (Phase 7)
- `GET /api/runs/{id}/export` — HTML report or ZIP bundle (Phase 8)

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
| 2026-04-08 | Phase 2 complete: Hunter module — async Semgrep CLI runner (timeout, error handling, exit code awareness) + deterministic findings normalizer (severity mapping, snippet extraction). Verified with sample Semgrep JSON. |
| 2026-04-08 | Pre-Phase 3 review: fixed severity ordering bug (CASE expression), added insert_findings_batch, expanded db.py smoke test (Run + Finding + TraceEvent). |
| 2026-04-08 | Phase 3 complete: SSE EventBus (publish/subscribe per run_id, auto-persists TraceEvents), GET /api/repos, POST /api/runs (bg scan task), GET /api/runs/{id}, GET /api/runs/{id}/stream (SSE). All routes wired into main.py. Verified with live server. |
| 2026-04-08 | Hunter expansion: Added hybrid scan pipeline. Finding model gets `confidence` field (float, Semgrep=1.0, LLM=0.6-0.9). TraceAction gets LLM_REVIEW_STARTED/COMPLETED. New `scanner/llm_reviewer.py` (Claude code review, skips Semgrep duplicates, structured JSON output). New `scanner/orchestrator.py` (two-phase pipeline, deduplication with 3-line tolerance, SSE publishing). `routes/runs.py` now delegates to orchestrator instead of calling Semgrep directly. DB schema updated with `confidence REAL` column. All verified. |
