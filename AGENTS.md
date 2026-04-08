# Vigil Agent Instructions

## Mission
Build Vigil, a multi-agent DevSecOps gatekeeper for vibe-coded repos.

## MVP Definition
The product must support this flow:
1. User selects one curated demo repo
2. System runs audit
3. Findings are displayed
4. User selects one finding
5. System proposes one minimal patch
6. Independent critic approves or rejects
7. Approved patch is verified in sandbox copy
8. UI shows before/after result
9. Export bundle is generated

## Hard Scope Boundaries
- MVP uses exactly three roles:
  - Hunter = hybrid scanner (deterministic Semgrep + LLM code review) with orchestrator
  - Surgeon = minimal patch generator
  - Critic = independent reviewer
- Only curated demo repos are in scope for the professor demo
- Demo repos must run reproducibly in Docker
- Verification means:
  - tests/lint/typecheck if configured
  - rerun the scanner that raised the issue
- Dependency vulnerabilities are report-first
- Auto-fixing dependencies is out of scope except safe patch bumps on curated repos

## Non-Goals
- Do not claim exploit-proof security closure for arbitrary repos
- Do not build “upload any repo and fully secure it” as a core demo
- Do not hide issues by disabling rules, loosening auth, or suppressing findings
- Do not make broad refactors when a minimal patch is enough

## Implementation Principles
- Prefer deterministic code over agent reasoning whenever possible
- The Hunter uses a hybrid pipeline: deterministic Semgrep first, then LLM review for logic flaws scanners miss. LLM findings are additive — they never block the pipeline.
- Every scanner output must normalize into typed Findings JSON with a confidence score
- Every patch proposal must target a single finding
- Every patch must be reviewable as a diff
- Critic must evaluate the patch independently
- Verification runs on a sandbox copy, not the original source tree
- Store trace events so the UI can show Hunter → Surgeon → Critic history

## Engineering Style
- Build the deterministic spine first, then the LLM features
- Keep functions small and typed
- No placeholder functions unless explicitly marked TODO
- No fake data paths in production code
- Every new route needs request/response schema
- Every major module needs a short module docstring/header comment

## Required Build Order
1. Contracts and data models
2. Scanner runner + findings normalization
3. Run API endpoints
4. Findings explorer backend
5. Patch proposal pipeline
6. Critic review pipeline
7. Verification pipeline
8. Export bundle
9. UI polish

## Agent Behavior
When asked to implement:
1. Read AGENTS.md and docs/*
2. Produce a plan first for multi-file changes
3. List files to change before editing
4. Make smallest viable change set
5. Run relevant tests/checks
6. Summarize what changed, what remains, and any risks
