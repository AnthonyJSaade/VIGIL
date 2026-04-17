"""Hunter orchestrator — two-phase scan pipeline with deduplication.

Phase 1: deterministic Semgrep scan (fast, high-confidence) — ``run_semgrep_scan``.
Phase 2: LLM-powered code review via Claude (catches logic flaws Semgrep misses) —
``run_llm_review_scan``.

The two phases can be invoked independently so the UI can display Semgrep
findings immediately and trigger the slower LLM review on demand. The
``run_full_scan`` helper remains for tests/automation that want the whole
pipeline in one call.
"""

import logging
from pathlib import Path

from ..db import get_findings_by_run, insert_findings_batch
from ..models.finding import Finding
from ..models.trace import AgentRole, TraceAction
from ..streaming.sse import bus
from .llm_reviewer import review_code
from .normalizer import normalize_findings
from .runner import run_semgrep

log = logging.getLogger(__name__)

_LINE_OVERLAP_TOLERANCE = 3


def _is_duplicate(llm_finding: Finding, semgrep_findings: list[Finding]) -> bool:
    """Return True if *llm_finding* overlaps a Semgrep finding on the same file
    within ``_LINE_OVERLAP_TOLERANCE`` lines."""
    for sf in semgrep_findings:
        if sf.file_path != llm_finding.file_path:
            continue
        if (
            llm_finding.start_line <= sf.end_line + _LINE_OVERLAP_TOLERANCE
            and llm_finding.end_line >= sf.start_line - _LINE_OVERLAP_TOLERANCE
        ):
            return True
    return False


async def run_semgrep_scan(run_id: str, repo_path: Path) -> list[Finding]:
    """Phase 1 only — run Semgrep, persist findings, publish SSE events.

    Returns the normalized findings. Raises ``ScanError`` from the runner on
    Semgrep failure so the caller can mark the run as failed.
    """
    await bus.publish(run_id, AgentRole.HUNTER, TraceAction.SCAN_STARTED, {"phase": "semgrep"})

    raw = await run_semgrep(repo_path)
    semgrep_findings = normalize_findings(raw, run_id, repo_path)

    for f in semgrep_findings:
        await bus.publish(
            run_id, AgentRole.HUNTER, TraceAction.FINDING_DISCOVERED,
            {"scanner": "semgrep", "rule_id": f.rule_id, "severity": f.severity.value, "file": f.file_path},
        )

    await insert_findings_batch(semgrep_findings)

    await bus.publish(run_id, AgentRole.HUNTER, TraceAction.SCAN_COMPLETED, {
        "phase": "semgrep",
        "total": len(semgrep_findings),
        "semgrep": len(semgrep_findings),
    })

    log.info("Semgrep phase: %d findings", len(semgrep_findings))
    return semgrep_findings


async def run_llm_review_scan(run_id: str, repo_path: Path) -> list[Finding]:
    """Phase 2 only — LLM code review, deduplicated against already-stored
    Semgrep findings for the run.

    Persists only the *new* (non-duplicate) LLM findings and publishes SSE
    events. LLM failures are non-fatal; any exception is logged and an empty
    list is returned so the run stays usable.
    """
    existing = await get_findings_by_run(run_id)
    semgrep_findings = [f for f in existing if f.scanner == "semgrep"]

    await bus.publish(run_id, AgentRole.HUNTER, TraceAction.LLM_REVIEW_STARTED, {
        "semgrep_count": len(semgrep_findings),
    })

    try:
        llm_findings = await review_code(repo_path, run_id, semgrep_findings)
    except Exception:  # noqa: BLE001 — LLM phase must never crash the run
        log.exception("LLM review failed for run %s", run_id)
        await bus.publish(run_id, AgentRole.HUNTER, TraceAction.LLM_REVIEW_COMPLETED, {
            "llm_count": 0,
            "error": "llm_review_failed",
        })
        return []

    unique_llm = [f for f in llm_findings if not _is_duplicate(f, semgrep_findings)]
    dropped = len(llm_findings) - len(unique_llm)
    if dropped:
        log.info("Deduplication dropped %d LLM findings that overlapped Semgrep results", dropped)

    for f in unique_llm:
        await bus.publish(
            run_id, AgentRole.HUNTER, TraceAction.FINDING_DISCOVERED,
            {"scanner": "claude-review", "rule_id": f.rule_id, "severity": f.severity.value, "file": f.file_path},
        )

    if unique_llm:
        await insert_findings_batch(unique_llm)

    await bus.publish(run_id, AgentRole.HUNTER, TraceAction.LLM_REVIEW_COMPLETED, {
        "llm_count": len(unique_llm),
    })

    log.info("LLM phase: %d findings (after dedup)", len(unique_llm))
    return unique_llm


async def run_full_scan(run_id: str, repo_path: Path) -> list[Finding]:
    """Run both phases sequentially. Used by tests/automation that want the
    whole pipeline. In the UI flow, the two phases are invoked separately."""
    semgrep_findings = await run_semgrep_scan(run_id, repo_path)
    llm_findings = await run_llm_review_scan(run_id, repo_path)
    return semgrep_findings + llm_findings
