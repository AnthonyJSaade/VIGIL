# VIGIL

**Multi-agent DevSecOps gatekeeper for vibe-coded repositories.**

Vigil audits AI-generated codebases using a team of specialized agents — a Hunter that finds vulnerabilities, a Surgeon that writes minimal patches, and a Critic that independently reviews them — with every step streamed to the UI in real time.

---

## How It Works

```
Select repo ─→ Hunter scans ─→ Pick a finding ─→ Surgeon patches ─→ Critic reviews ─→ Verify in sandbox ─→ Export report
```

1. **Select** a curated demo repository (e.g. a "vibe-coded" Express.js app)
2. **Hunter** runs a two-phase scan: deterministic Semgrep first, then Claude code review for logic flaws scanners miss
3. **Browse findings** sorted by severity, filterable by scanner source, with confidence scores
4. **Surgeon** generates a minimal unified diff targeting a single vulnerability
5. **Critic** independently reviews the patch — if rejected, Surgeon retries once incorporating the Critic's concerns
6. **Verify** in a sandbox copy: apply the patch, rerun the scanner, confirm the finding is gone
7. **Export** a self-contained HTML report or ZIP bundle

All agent steps stream to the browser via Server-Sent Events (SSE) so the entire pipeline is watchable, not just clickable.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Next.js Frontend                                        │
│  ┌──────────┐  ┌───────────────┐  ┌──────────────────┐  │
│  │ Repo     │  │ Findings      │  │ Finding Detail   │  │
│  │ Picker   │  │ Dashboard     │  │ + Patch + Verify │  │
│  └────┬─────┘  └──────┬────────┘  └────────┬─────────┘  │
│       │  SSE EventSource  │                  │           │
└───────┼──────────────────┼──────────────────┼────────────┘
        │ HTTP             │                  │
┌───────┴──────────────────┴──────────────────┴────────────┐
│  FastAPI Backend                                         │
│                                                          │
│  ┌─────────── Hunter ────────────┐                       │
│  │ Semgrep CLI → Claude Review   │                       │
│  │        → Deduplicate          │                       │
│  └───────────────────────────────┘                       │
│  ┌── Surgeon ──┐  ┌── Critic ──┐  ┌── Verifier ──┐     │
│  │ Claude      │←→│ Claude     │  │ Sandbox copy │     │
│  │ patch gen   │  │ review     │  │ + rerun scan │     │
│  └─────────────┘  └────────────┘  └──────────────┘     │
│                                                          │
│  SQLite │ SSE Event Bus │ Export (HTML/ZIP)               │
└──────────────────────────────────────────────────────────┘
```

### Agent Roles

| Agent | Type | Purpose |
|-------|------|---------|
| **Hunter** | Hybrid (Semgrep + Claude) | Phase 1: deterministic static analysis. Phase 2: LLM code review for logic flaws, auth gaps, and issues rule-based scanners miss. Deduplicates overlapping findings. |
| **Surgeon** | LLM (Claude) | Generates a minimal unified diff for a single finding. Supports retry with Critic feedback on rejection. |
| **Critic** | LLM (Claude) | Independently reviews the patch with no access to Surgeon's reasoning. Approves or rejects with a list of specific concerns. |
| **Verifier** | Deterministic | Copies the repo to a temp directory, applies the diff, reruns Semgrep, and confirms the vulnerability no longer fires. |

### Key Design Decisions

- **Deterministic spine, LLM features on top.** Scanner execution, verification, persistence, and API behavior are all deterministic. LLMs explain, patch, and critique.
- **LLM findings are additive.** If the Claude code review fails or times out, Semgrep results still get through. The pipeline never blocks on an LLM call.
- **Confidence scores.** Semgrep findings have confidence 1.0 (certain). LLM findings carry a self-assessed confidence (0.0–1.0) so the UI can distinguish them.
- **Feedback loop.** On rejection, Surgeon gets one retry with the Critic's specific concerns — real multi-agent interaction, not just sequential calls.
- **Full traceability.** Every agent action is stored as a `TraceEvent` and streamed via SSE, enabling a complete audit trail.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, Pydantic |
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS |
| Scanner | Semgrep CLI + Anthropic Claude |
| LLM | Anthropic Claude (via `anthropic` SDK) |
| Database | SQLite (aiosqlite) |
| Streaming | Server-Sent Events (SSE) via asyncio.Queue |
| Export | Self-contained HTML report (Jinja2) + ZIP bundle |

## Project Structure

```
.
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # FastAPI app, CORS, lifespan
│       ├── config.py            # Settings (env: VIGIL_*)
│       ├── db.py                # SQLite schema + async CRUD
│       ├── models/              # Pydantic schemas
│       ├── scanner/             # Hunter (hybrid pipeline)
│       │   ├── runner.py        # Semgrep CLI wrapper
│       │   ├── normalizer.py    # Semgrep JSON → Finding[]
│       │   ├── llm_reviewer.py  # Claude code review → Finding[]
│       │   └── orchestrator.py  # Two-phase scan + deduplication
│       ├── agents/              # LLM-backed agents
│       │   ├── surgeon.py       # Finding → unified diff
│       │   ├── critic.py        # Diff → verdict
│       │   └── orchestrator.py  # Surgeon-Critic feedback loop
│       ├── verification/
│       │   └── sandbox.py       # Copy repo, apply patch, rerun scanner
│       ├── export/
│       │   ├── bundle.py        # HTML report + ZIP generation
│       │   └── report_template.html
│       ├── streaming/
│       │   └── sse.py           # EventBus (publish/subscribe per run)
│       └── routes/              # API endpoints
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── app/                     # Next.js App Router pages
│   │   ├── page.tsx             # Home — repo picker
│   │   └── audit/[id]/
│   │       ├── page.tsx         # Audit — SSE timeline + findings
│   │       ├── finding/[findingId]/
│   │       │   └── page.tsx     # Finding detail + patch pipeline
│   │       └── patch-all/
│   │           └── page.tsx     # Batch patch all findings
│   ├── components/
│   │   ├── ui/                  # shadcn/ui components
│   │   └── vigil/               # Vigil-specific components
│   └── lib/
│       ├── api.ts               # Typed fetch wrappers (snake→camel)
│       └── utils.ts             # cn() utility
├── demo-repos/
│   └── vibe-todo-app/           # Intentionally vulnerable Express.js app
│       └── server.js            # 9 vulns (5 Semgrep + 4 LLM-only)
├── docker-compose.yml
├── .env.example
├── AGENTS.md                    # Project charter + agent rules
├── PLAN.md                      # Full implementation plan
└── CONTEXT.md                   # Build context for session continuity
```

## Getting Started

### Quick Start with Docker

```bash
cp .env.example .env
# Edit .env and add your Anthropic API key

docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

### Local Development

#### Prerequisites

- Python 3.11+
- Node.js 18+
- [Semgrep](https://semgrep.dev/docs/getting-started/) (`pip install semgrep`)
- An [Anthropic API key](https://console.anthropic.com/)

#### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export VIGIL_ANTHROPIC_API_KEY="sk-ant-..."
export VIGIL_SURGEON_MODEL="claude-sonnet-4-6"
export VIGIL_CRITIC_MODEL="claude-sonnet-4-6"

uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `/docs`.

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI will be available at `http://localhost:3000`.

### Demo Repository

The project ships with `demo-repos/vibe-todo-app/` — a deliberately vulnerable Express.js todo API designed to showcase both scanning phases:

- **Semgrep detects** (confidence 1.0): SQL injection, hardcoded JWT secret, eval(), permissive CORS, path traversal
- **LLM review detects** (confidence 0.6-0.8): missing rate limiting, no input validation, logging passwords, error stack leakage

### Environment Variables

All backend settings use the `VIGIL_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `VIGIL_ANTHROPIC_API_KEY` | `""` | Anthropic API key for Claude (required for LLM features) |
| `VIGIL_SURGEON_MODEL` | `claude-sonnet-4-6` | Model ID used by the Surgeon when generating patches |
| `VIGIL_CRITIC_MODEL` | `claude-sonnet-4-6` | Model ID used by the Critic when reviewing patches |
| `VIGIL_DB_PATH` | `vigil.db` | Path to the SQLite database file |
| `VIGIL_DEMO_REPOS_PATH` | `../demo-repos` | Path to the directory containing curated demo repositories |

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/repos` | List curated demo repositories |
| `POST` | `/api/runs` | Start an audit run (launches scan in background) |
| `GET` | `/api/runs/{id}` | Get run metadata and status |
| `GET` | `/api/runs/{id}/stream` | SSE event stream for real-time updates |
| `GET` | `/api/runs/{id}/findings` | List findings (filterable by `severity`, `scanner`) |
| `GET` | `/api/findings/{id}` | Get single finding detail |
| `POST` | `/api/findings/{id}/patch` | Trigger Surgeon-Critic feedback loop (202 Accepted) |
| `GET` | `/api/findings/{id}/patches` | List all patch attempts with verdicts |
| `POST` | `/api/patches/{id}/verify` | Trigger sandbox verification (requires Critic approval) |
| `GET` | `/api/patches/{id}/verification` | Get verification result |
| `GET` | `/api/runs/{id}/export?format=html` | Download self-contained HTML report |
| `GET` | `/api/runs/{id}/export?format=zip` | Download ZIP bundle (report + JSON + diffs) |

## Data Models

| Model | Key Fields |
|-------|-----------|
| `Run` | id, repo_id, status (pending/scanning/completed/failed), finding_count |
| `Finding` | id, run_id, scanner, rule_id, severity (error/warning/info), message, file_path, start_line, end_line, snippet, confidence |
| `PatchProposal` | id, finding_id, diff, explanation, model_used, attempt (1 or 2), prior_concerns |
| `CriticVerdict` | id, patch_id, approved, reasoning, concerns[] |
| `VerificationReport` | id, patch_id, scanner_rerun_clean, tests_passed, details |
| `TraceEvent` | id, run_id, role (hunter/surgeon/critic/verifier), action, payload, timestamp |

## SSE Event Types

Events stream through `GET /api/runs/{id}/stream` as JSON payloads:

| Action | Agent | When |
|--------|-------|------|
| `scan_started` | Hunter | Audit begins |
| `finding_discovered` | Hunter | Each finding (Semgrep or LLM) |
| `llm_review_started` | Hunter | Claude code review begins |
| `llm_review_completed` | Hunter | Claude code review finishes |
| `scan_completed` | Hunter | All scanning done |
| `patch_proposed` | Surgeon | Diff generated |
| `review_started` | Critic | Patch review begins |
| `review_approved` | Critic | Patch accepted |
| `review_rejected` | Critic | Patch rejected with concerns |
| `patch_retried` | Surgeon | Retry with Critic feedback |
| `verification_started` | Verifier | Sandbox verification begins |
| `verification_completed` | Verifier | Verification result ready |

## Export

The export endpoint generates a self-contained HTML report with:

- Dark theme with agent color-coding (Hunter=teal, Surgeon=amber, Critic=purple, Verifier=green)
- Summary statistics (findings by severity, patch approval rate)
- Findings table with severity badges, confidence bars, and scanner source
- Syntax-highlighted diffs for each patch attempt
- Critic verdicts and verification results
- Full agent trace timeline
- Print-friendly CSS

The ZIP bundle includes the HTML report plus raw JSON files (findings, trace events) and individual diff files for each patch.

## License

This project was built as a university demo. Not intended for production security assessments.
