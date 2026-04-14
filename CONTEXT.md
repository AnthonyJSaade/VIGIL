# Vigil — Build Context

> This file tracks the current state of the build so any new chat session can pick up where we left off.
> Updated after each significant change.

## Last Updated
2026-04-14

## Current Phase
**Phase 9 complete + post-review fixes** — Full Next.js UI wired to all backend endpoints. Repo picker → Start Audit → live SSE feed → findings list → finding detail with code snippet → patch request + Critic verdict → sandbox verification → export download. Post-review sweep fixed SSE delivery bug, patch polling race condition, missing error handling, and React lint warnings. Ready for Phase 10 (demo repo + Docker).

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
| `backend/app/agents/surgeon.py` | `propose_patch(finding, file_content, prior_concerns?, attempt?) -> PatchProposal`. Calls Claude. Produces unified diff + explanation. Supports retry with Critic feedback. |
| `backend/app/agents/critic.py` | `review_patch(finding, patch, file_content) -> CriticVerdict`. Independent Claude call — no access to Surgeon's reasoning. Returns approved/rejected with concerns list. |
| `backend/app/agents/orchestrator.py` | `run_patch_review_loop(finding_id, repo_path) -> (PatchProposal, CriticVerdict)`. Surgeon-Critic feedback loop, max 2 attempts. Publishes SSE events at each step. |
| `backend/app/verification/sandbox.py` | `verify_patch(patch, finding, repo_path) -> VerificationReport`. Copies repo to temp dir, applies unified diff via `patch -p1`, reruns Semgrep, checks if original rule no longer fires. |
| `backend/app/routes/findings.py` | `GET /api/runs/{run_id}/findings` (filterable), `GET /api/findings/{id}` (detail), `POST /api/findings/{id}/patch` (trigger Surgeon-Critic loop), `GET /api/findings/{id}/patches` (list patch attempts with verdicts). |
| `backend/app/routes/patches.py` | `POST /api/patches/{id}/verify` — triggers sandbox verification (only if Critic approved, 202). `GET /api/patches/{id}/verification` — returns verification result. |
| `backend/app/routes/stream.py` | `GET /api/runs/{id}/stream` — SSE endpoint via StreamingResponse |
| `backend/app/export/__init__.py` | Export module package marker |
| `backend/app/export/report_template.html` | Jinja2 template — self-contained HTML with embedded CSS, dark theme, agent color-coding (hunter=teal, surgeon=amber, critic=purple, verifier=green), diff syntax highlighting, trace timeline. Print-friendly. |
| `backend/app/export/bundle.py` | `generate_html_report(run_id) -> str` and `generate_zip_bundle(run_id) -> bytes`. Collects all run data (findings, patches, verdicts, verifications, trace events), renders template. ZIP includes report.html + findings.json + trace.json + individual diffs and verdicts. |
| `backend/app/routes/export.py` | `GET /api/runs/{run_id}/export?format=html|zip` — downloads self-contained HTML report or ZIP bundle. Content-Disposition attachment headers. 404 if run not found. |
| `frontend/package.json` | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4 (`@tailwindcss/postcss`), ESLint (`eslint-config-next`) |
| `frontend/next.config.ts` | Default Next config scaffold |
| `frontend/src/app/layout.tsx` | Root layout: Geist / Geist Mono fonts, `globals.css`, metadata set to "VIGIL — DevSecOps Gatekeeper" |
| `frontend/src/app/globals.css` | Tailwind v4 entry (`@import "tailwindcss"`) |
| `frontend/src/app/page.tsx` | Home (async server component): `fetch("http://localhost:8000/api/repos", { cache: "no-store" })`, maps JSON to `Repo[]`, renders `RepoCards` |
| `frontend/src/app/repo-cards.tsx` | Client component: responsive repo card grid, selection toggle, "Start Audit" button calls `POST /api/runs` and navigates to `/runs/{id}` |
| `frontend/src/app/runs/[run_id]/page.tsx` | Run page: fetches run status, renders `LiveFeed` (SSE), `FindingsList` on completion, export download links |
| `frontend/src/app/findings/[finding_id]/page.tsx` | Finding detail: severity badge, code snippet with line numbers, confidence %, `PatchPanel` for Surgeon-Critic flow |
| `frontend/src/components/live-feed.tsx` | SSE client via `EventSource`: connects to `/api/runs/{id}/stream`, renders scrolling agent event log with role colors |
| `frontend/src/components/findings-list.tsx` | Filterable findings grid (by severity), links each finding to its detail page |
| `frontend/src/components/severity-badge.tsx` | Colored severity pill (error=red, warning=yellow, info=blue) |
| `frontend/src/components/patch-panel.tsx` | Patch request button, polls for results, renders unified diff (color-coded), Critic verdict, "Verify in Sandbox" button, verification result display |

## What Does NOT Exist Yet
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
- `GET /api/runs/{run_id}/findings` — findings list (filterable by severity, scanner)
- `GET /api/findings/{id}` — single finding detail with snippet + metadata
- `POST /api/findings/{id}/patch` — trigger Surgeon-Critic feedback loop (bg task, 202)
- `GET /api/findings/{id}/patches` — list all patch attempts with verdicts
- `POST /api/patches/{id}/verify` — trigger sandbox verification (only if Critic approved, 202)
- `GET /api/patches/{id}/verification` — verification result

- `GET /api/runs/{id}/export?format=html|zip` — export HTML report or ZIP bundle (attachment download)

All backend API endpoints are now implemented.

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
- 2-person team (Anthony: backend + repo root through Phase 8; Michael: `frontend/` Next.js scaffold and repo-selection UI)

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
| 2026-04-08 | Phase 4 complete: Findings explorer — `GET /api/runs/{run_id}/findings` (filterable by severity and scanner) + `GET /api/findings/{id}` (full detail with snippet + metadata). Wired into main.py. |
| 2026-04-08 | Phases 5+6 complete: Surgeon agent (`agents/surgeon.py`) generates minimal unified diffs via Claude. Critic agent (`agents/critic.py`) independently reviews patches — no access to Surgeon reasoning. Feedback loop orchestrator (`agents/orchestrator.py`) runs max 2 attempts with Critic concerns fed back to Surgeon. `POST /api/findings/{id}/patch` triggers the loop as a bg task (202). `GET /api/findings/{id}/patches` returns all attempts with verdicts. All SSE events published. |
| 2026-04-08 | Phase 7 complete: Verification pipeline — `verification/sandbox.py` copies repo to temp dir, applies diff via `patch -p1`, reruns Semgrep, checks if original rule no longer fires. `routes/patches.py` adds `POST /api/patches/{id}/verify` (only if Critic approved) and `GET /api/patches/{id}/verification`. SSE events for verification_started/completed. |
| 2026-04-08 | Pre-Phase 8 review: fixed 3 bugs (silent patch pipeline failure on SSE, bus.close() never called, dead _read_source_file) + 2 hygiene issues (lazy imports, unused import). |
| 2026-04-08 | Phase 8 complete: Export bundle — `export/report_template.html` (Jinja2, self-contained dark theme, agent color-coding, diff rendering, trace timeline, print-friendly). `export/bundle.py` collects all run data, renders HTML or generates ZIP (report + JSON + diffs). `routes/export.py` serves `GET /api/runs/{id}/export?format=html|zip`. All backend API endpoints now implemented. |
| 2026-04-13 | Phase 9 kickoff: scaffolded Next.js app under `frontend/` (TypeScript, Tailwind v4, App Router). Home at `src/app/page.tsx` fetches curated repos from `http://localhost:8000/api/repos` (no-store). `repo-cards.tsx` client grid for selecting a repo (local selection state only; not wired to `POST /api/runs` yet). |
| 2026-04-13 | Phase 9 complete: Full MVP UI built. (1) "Start Audit" button in `repo-cards.tsx` calls `POST /api/runs` and navigates to run page. (2) `/runs/[run_id]` page with SSE live feed (`EventSource`), findings list on completion, export buttons. (3) `/findings/[finding_id]` page with code snippet, confidence score, patch request + diff viewer, Critic verdict panel, sandbox verification trigger and result. (4) Shared components: `live-feed.tsx`, `findings-list.tsx`, `severity-badge.tsx`, `patch-panel.tsx`. (5) Layout metadata updated. Build passes cleanly (TypeScript + Next.js). |
| 2026-04-14 | Post-review bug fixes: (1) **SSE delivery fix** — removed named `event:` field from SSE frames in `backend/app/streaming/sse.py` so `EventSource.onmessage` receives events (action is already in the JSON payload). (2) **Patch polling race fix** — `patch-panel.tsx` now keeps polling until a patch is approved or all 2 attempts are exhausted, instead of stopping at the first result (which hid the Critic retry). (3) **Home page error handling** — `page.tsx` catches backend-down errors and shows a fallback message instead of crashing. (4) **React lint fix** — wrapped `fetchRun` in `useCallback` in `runs/[run_id]/page.tsx` so dependency arrays are correct. (5) **Poll resilience** — `loadPatches` now catches network errors instead of throwing uncaught rejections every 2 s. (6) **Comment style alignment** — added JSDoc to complex functions in `patch-panel.tsx` and fixed header comment format in `severity-badge.tsx` to match backend docstring conventions. Build passes cleanly. |
