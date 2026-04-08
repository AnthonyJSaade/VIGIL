"""Hunter orchestrator — two-phase scan pipeline with deduplication.

Phase 1: deterministic Semgrep scan (fast, high-confidence).
Phase 2: LLM-powered code review via Claude (catches logic flaws Semgrep misses).

The orchestrator merges and deduplicates findings from both phases, publishes
SSE events throughout, and returns the final finding list.
"""

import logging
from pathlib import Path

from ..db import insert_findings_batch
from ..models.finding import Finding
from ..models.trace import AgentRole, TraceAction
from ..streaming.sse import bus
from .llm_reviewer import review_code
from .normalizer import normalize_findings
from .runner import ScanError, run_semgrep

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


def _deduplicate(
    semgrep_findings: list[Finding],
    llm_findings: list[Finding],
) -> list[Finding]:
    """Merge both lists, dropping LLM findings that overlap existing Semgrep ones."""
    unique_llm = [f for f in llm_findings if not _is_duplicate(f, semgrep_findings)]
    dropped = len(llm_findings) - len(unique_llm)
    if dropped:
        log.info("Deduplication dropped %d LLM findings that overlapped Semgrep results", dropped)
    return semgrep_findings + unique_llm


async def run_full_scan(run_id: str, repo_path: Path) -> list[Finding]:
    """Execute the full Hunter pipeline and return deduplicated findings.

    Publishes SSE events at each stage. On Semgrep failure the entire scan
    aborts (Semgrep is the deterministic backbone). LLM review failures are
    non-fatal — the pipeline returns whatever Semgrep found.
    """
    # ── Phase 1: Semgrep ────────────────────────────────────────────────
    await bus.publish(run_id, AgentRole.HUNTER, TraceAction.SCAN_STARTED, {"phase": "semgrep"})

    raw = await run_semgrep(repo_path)
    semgrep_findings = normalize_findings(raw, run_id)

    for f in semgrep_findings:
        await bus.publish(
            run_id, AgentRole.HUNTER, TraceAction.FINDING_DISCOVERED,
            {"scanner": "semgrep", "rule_id": f.rule_id, "severity": f.severity.value, "file": f.file_path},
        )

    log.info("Semgrep phase: %d findings", len(semgrep_findings))

    # ── Phase 2: LLM review ────────────────────────────────────────────
    await bus.publish(run_id, AgentRole.HUNTER, TraceAction.LLM_REVIEW_STARTED, {
        "semgrep_count": len(semgrep_findings),
    })

    llm_findings = await review_code(repo_path, run_id, semgrep_findings)

    for f in llm_findings:
        await bus.publish(
            run_id, AgentRole.HUNTER, TraceAction.FINDING_DISCOVERED,
            {"scanner": "claude-review", "rule_id": f.rule_id, "severity": f.severity.value, "file": f.file_path},
        )

    await bus.publish(run_id, AgentRole.HUNTER, TraceAction.LLM_REVIEW_COMPLETED, {
        "llm_count": len(llm_findings),
    })

    log.info("LLM phase: %d findings", len(llm_findings))

    # ── Merge + deduplicate ─────────────────────────────────────────────
    all_findings = _deduplicate(semgrep_findings, llm_findings)

    await insert_findings_batch(all_findings)

    await bus.publish(run_id, AgentRole.HUNTER, TraceAction.SCAN_COMPLETED, {
        "total": len(all_findings),
        "semgrep": len(semgrep_findings),
        "llm": len(all_findings) - len(semgrep_findings),
    })

    return all_findings
