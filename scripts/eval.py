"""Vigil evaluation harness — single-command end-to-end eval.

Runs the real Hunter, Surgeon, Critic, and Verifier agents against every
curated demo repo that ships with a `.vigil/truth.yaml` manifest, matches
reported findings against ground truth, and emits Markdown + JSON reports.

In-process only: no HTTP layer, no SSE subscribers. The agents still publish
trace events but they land in idle asyncio queues that the harness never
subscribes to, so nothing is buffered indefinitely.

Usage:
    python scripts/eval.py                          # full eval on all repos
    python scripts/eval.py --repos vibe-notes-api   # single repo
    python scripts/eval.py --hunter-only            # skip patch/critic/verify
    python scripts/eval.py --skip-llm-review        # Semgrep-only Hunter
    python scripts/eval.py --out eval-artifacts/custom/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
for _path in (str(REPO_ROOT), str(BACKEND_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _load_dotenv() -> None:
    """Best-effort `.env` loader so ``VIGIL_ANTHROPIC_API_KEY`` is available
    when the harness is invoked from a plain shell. No third-party dep."""
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()

# Semgrep's first invocation (or first after a stale cache) can block on
# fetching `--config auto` rules from the registry. The backend defaults to a
# 2-minute timeout, which is friendly for API requests but too tight for an
# end-to-end eval that may start cold. Give the eval process 10 minutes per
# scan unless the caller already overrode the env var.
os.environ.setdefault("VIGIL_SEMGREP_TIMEOUT_SECONDS", "600")

from scripts.eval_matching import (  # noqa: E402
    Match,
    MatchResult,
    ReportedFinding,
    TruthFinding,
    match_findings,
)
from scripts.eval_report import render_markdown, render_summary_json  # noqa: E402

log = logging.getLogger("vigil.eval")


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class FindingRow:
    """Flat record captured per reported finding for reporting/audit."""

    finding_id: str
    scanner: str
    rule_id: str
    severity: str
    file_path: str
    start_line: int
    end_line: int
    confidence: float
    matched_truth_id: str | None = None
    match_reason: str | None = None
    match_distance: int | None = None
    is_duplicate: bool = False


@dataclass
class PipelineRow:
    """Per-truth-entry record of the full scan-to-fix journey."""

    truth_id: str
    detected: bool = False
    detected_by: str | None = None
    finding_id: str | None = None
    patch_id: str | None = None
    patch_attempt: int | None = None
    critic_approved: bool | None = None
    verification_clean: bool | None = None
    verification_details: str | None = None
    scan_time_s: float | None = None
    patch_time_s: float | None = None
    verify_time_s: float | None = None


@dataclass
class RepoResult:
    repo_id: str
    language: str
    loc: int
    truth: list[dict] = field(default_factory=list)
    findings: list[FindingRow] = field(default_factory=list)
    pipeline: list[PipelineRow] = field(default_factory=list)
    unmatched_finding_ids: list[str] = field(default_factory=list)
    scan_wallclock_s: float = 0.0
    hunter_metrics: dict = field(default_factory=dict)
    surgeon_metrics: dict = field(default_factory=dict)
    critic_metrics: dict = field(default_factory=dict)
    end_to_end: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_loc(repo_path: Path) -> int:
    """Count lines of code across source files we care about. Ignores deps."""
    skip_parts = {"node_modules", ".venv", "venv", "__pycache__", ".git"}
    extensions = {".py", ".js", ".ts", ".html"}
    total = 0
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        if path.suffix not in extensions:
            continue
        try:
            total += sum(1 for _ in path.read_text(errors="ignore").splitlines())
        except OSError:
            continue
    return total


def _load_truth(repo_path: Path) -> list[TruthFinding]:
    import yaml

    manifest = repo_path / ".vigil" / "truth.yaml"
    if not manifest.is_file():
        return []
    doc = yaml.safe_load(manifest.read_text())
    entries = doc.get("findings", []) if isinstance(doc, dict) else []
    return [TruthFinding.from_yaml_entry(e) for e in entries]


def _truth_to_dict(t: TruthFinding) -> dict:
    return {
        "id": t.id,
        "cwe": t.cwe,
        "kind": t.kind,
        "file": t.file,
        "lines": list(t.lines),
        "severity": t.severity,
        "detectable_by": sorted(t.detectable_by),
        "notes": t.notes,
    }


def _percentile(samples: list[float], pct: float) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    k = (len(ordered) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    frac = k - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _pct_fmt(num: float | None) -> float:
    if num is None:
        return 0.0
    return round(num, 4)


def _safe_div(n: float, d: float) -> float:
    return n / d if d else 0.0


# ---------------------------------------------------------------------------
# Backend wiring
# ---------------------------------------------------------------------------


def _init_backend_for(eval_db_path: Path) -> None:
    """Point the backend's global settings at our throwaway DB.

    Must be called before any backend module with a DB-touching import is used.
    Attribute-mutating the singleton is enough because :mod:`db` reads
    ``settings.db_path`` inside every helper, not once at import time.
    """
    from app.config import settings

    settings.db_path = str(eval_db_path)


async def _new_eval_db(eval_db_path: Path) -> None:
    """Create fresh schema in the throwaway eval DB."""
    from app.db import init_db

    if eval_db_path.exists():
        eval_db_path.unlink()
    await init_db()


def _cwe_from_metadata(metadata: dict) -> str | None:
    """Extract a CWE id from a finding's metadata, best-effort."""
    cwe = metadata.get("cwe")
    if isinstance(cwe, str):
        return cwe
    if isinstance(cwe, list) and cwe:
        return cwe[0] if isinstance(cwe[0], str) else None
    return None


def _to_reported(findings) -> list[ReportedFinding]:  # noqa: ANN001
    out = []
    for f in findings:
        metadata = f.metadata if isinstance(f.metadata, dict) else {}
        out.append(
            ReportedFinding(
                id=f.id,
                scanner=f.scanner,
                rule_id=f.rule_id,
                file_path=f.file_path,
                start_line=f.start_line,
                end_line=f.end_line,
                metadata_cwe=_cwe_from_metadata(metadata),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Per-repo pipeline
# ---------------------------------------------------------------------------


async def _run_hunter(run_id: str, repo_path: Path, skip_llm: bool):  # noqa: ANN201
    from app.scanner.orchestrator import run_llm_review_scan, run_semgrep_scan

    await run_semgrep_scan(run_id, repo_path)
    if not skip_llm:
        try:
            await run_llm_review_scan(run_id, repo_path)
        except Exception:  # noqa: BLE001
            log.exception("LLM review failed for run %s (continuing)", run_id)

    from app.db import get_findings_by_run

    return await get_findings_by_run(run_id)


async def _run_patch_pipeline(
    finding_id: str, repo_path: Path
) -> tuple[str, int, bool] | None:
    """Drive Surgeon + Critic for one finding. Returns
    ``(patch_id, attempt, approved)`` on success or ``None`` on crash."""
    from app.agents.orchestrator import run_patch_review_loop

    try:
        patch, verdict = await run_patch_review_loop(finding_id, repo_path)
    except Exception:  # noqa: BLE001
        log.exception("Surgeon-Critic loop crashed for finding %s", finding_id)
        return None
    return patch.id, patch.attempt, verdict.approved


async def _run_verifier(
    patch_id: str, finding_id: str, repo_path: Path
) -> tuple[bool, str] | None:
    from app.db import get_finding, get_patch, insert_verification
    from app.verification.sandbox import verify_patch

    patch = await get_patch(patch_id)
    finding = await get_finding(finding_id)
    if patch is None or finding is None:
        return None
    try:
        report = await verify_patch(patch, finding, repo_path)
    except Exception:  # noqa: BLE001
        log.exception("Verifier crashed for patch %s", patch_id)
        return None
    await insert_verification(report)
    return report.scanner_rerun_clean, report.details


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------


def _compute_hunter_metrics(
    findings: list[FindingRow],
    truth: list[TruthFinding],
    match_result: MatchResult,
) -> dict:
    truth_by_id = {t.id: t for t in truth}

    def _tally(scanner_filter: set[str] | None) -> dict:
        relevant_findings = [
            f for f in findings if scanner_filter is None or f.scanner in scanner_filter
        ]
        reported_ids = {f.finding_id for f in relevant_findings}
        relevant_matches = [m for m in match_result.matches if m.finding_id in reported_ids]
        fp = len(
            [
                f
                for f in relevant_findings
                if f.matched_truth_id is None and not f.is_duplicate
            ]
        )

        if scanner_filter == {"semgrep"}:
            expected = [t for t in truth if "semgrep" in t.detectable_by]
        elif scanner_filter == {"claude-review"}:
            expected = [t for t in truth if "llm" in t.detectable_by]
        else:
            expected = list(truth)
        expected_ids = {t.id for t in expected}
        matched_ids = {m.truth_id for m in relevant_matches}

        # Recall is measured against each scanner's expected set so a scanner
        # isn't rewarded for outperforming its `detectable_by` tag or punished
        # for bugs the manifest says belong to another scanner.
        tp = len(matched_ids & expected_ids)
        fn = len(expected_ids - matched_ids)
        bonus = len(matched_ids - expected_ids)

        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        return {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "bonus": bonus,
            "expected": len(expected_ids),
            "precision": _pct_fmt(precision),
            "recall": _pct_fmt(recall),
            "f1": _pct_fmt(f1),
        }

    semgrep = _tally({"semgrep"})
    llm = _tally({"claude-review"})
    combined = _tally(None)

    semgrep_hits = {
        m.truth_id
        for m in match_result.matches
        if any(f.finding_id == m.finding_id and f.scanner == "semgrep" for f in findings)
    }
    llm_hits = {
        m.truth_id
        for m in match_result.matches
        if any(
            f.finding_id == m.finding_id and f.scanner == "claude-review" for f in findings
        )
    }
    llm_only_contributions = sorted(llm_hits - semgrep_hits)
    llm_only_truth_entries = [
        truth_by_id[tid].kind for tid in llm_only_contributions if tid in truth_by_id
    ]

    return {
        "semgrep": semgrep,
        "llm": llm,
        "combined": combined,
        "llm_only_contribution_count": len(llm_only_contributions),
        "llm_only_contribution_truth_ids": llm_only_contributions,
        "llm_only_contribution_kinds": llm_only_truth_entries,
    }


def _compute_surgeon_metrics(pipeline: list[PipelineRow]) -> dict:
    patched = [p for p in pipeline if p.patch_id is not None]
    if not patched:
        return {
            "patches_attempted": 0,
            "apply_rate": 0.0,
            "mean_attempts": 0.0,
            "retry_rate": 0.0,
            "attempt_distribution": {},
        }

    applied = [p for p in patched if p.verification_clean is not None]
    applied_ok = [p for p in patched if p.verification_details is not None and p.verification_clean is not None and "Patch failed to apply" not in (p.verification_details or "")]

    attempts = [p.patch_attempt or 1 for p in patched]
    distribution: dict[int, int] = {}
    for a in attempts:
        distribution[a] = distribution.get(a, 0) + 1

    retries = [a for a in attempts if a > 1]
    return {
        "patches_attempted": len(patched),
        "apply_rate": _pct_fmt(_safe_div(len(applied_ok), len(applied) or len(patched))),
        "mean_attempts": _pct_fmt(sum(attempts) / len(attempts)),
        "retry_rate": _pct_fmt(_safe_div(len(retries), len(patched))),
        "attempt_distribution": distribution,
    }


def _compute_critic_metrics(pipeline: list[PipelineRow]) -> dict:
    verdicts = [p for p in pipeline if p.critic_approved is not None]
    if not verdicts:
        return {
            "verdicts": 0,
            "approval_rate": 0.0,
            "approved": 0,
            "rejected": 0,
            "agreement_with_verifier": 0.0,
            "false_accept_rate": 0.0,
        }
    approved = [p for p in verdicts if p.critic_approved]
    rejected = [p for p in verdicts if not p.critic_approved]
    approved_verified = [p for p in approved if p.verification_clean is True]
    approved_dirty = [p for p in approved if p.verification_clean is False]

    return {
        "verdicts": len(verdicts),
        "approved": len(approved),
        "rejected": len(rejected),
        "approval_rate": _pct_fmt(_safe_div(len(approved), len(verdicts))),
        "agreement_with_verifier": _pct_fmt(
            _safe_div(len(approved_verified), len(approved_verified) + len(approved_dirty))
        ),
        "false_accept_rate": _pct_fmt(
            _safe_div(len(approved_dirty), len(approved_verified) + len(approved_dirty))
        ),
    }


def _compute_end_to_end(pipeline: list[PipelineRow], truth_count: int) -> dict:
    detected = [p for p in pipeline if p.detected]
    patched = [p for p in detected if p.patch_id is not None]
    approved = [p for p in patched if p.critic_approved]
    verified = [p for p in approved if p.verification_clean is True]

    return {
        "truth_total": truth_count,
        "detected": len(detected),
        "patched": len(patched),
        "approved": len(approved),
        "verified_clean": len(verified),
        "fix_rate": _pct_fmt(_safe_div(len(verified), truth_count)),
        "detection_rate": _pct_fmt(_safe_div(len(detected), truth_count)),
    }


def _compute_timings(pipeline: list[PipelineRow], scan_wallclock: float) -> dict:
    patch_times = [p.patch_time_s for p in pipeline if p.patch_time_s is not None]
    verify_times = [p.verify_time_s for p in pipeline if p.verify_time_s is not None]
    return {
        "scan_wallclock_s": round(scan_wallclock, 2),
        "patch_loop_p50_s": round(_percentile(patch_times, 0.5) or 0.0, 2),
        "patch_loop_p95_s": round(_percentile(patch_times, 0.95) or 0.0, 2),
        "verify_p50_s": round(_percentile(verify_times, 0.5) or 0.0, 2),
        "verify_p95_s": round(_percentile(verify_times, 0.95) or 0.0, 2),
    }


# ---------------------------------------------------------------------------
# Main per-repo driver
# ---------------------------------------------------------------------------


async def _eval_repo(
    repo_id: str,
    repo_path: Path,
    *,
    hunter_only: bool,
    skip_llm: bool,
) -> RepoResult:
    from app.db import insert_run
    from app.models.run import Run, RunStatus

    log.info("=== %s ===", repo_id)

    truth = _load_truth(repo_path)
    if not truth:
        log.warning("No truth manifest found for %s; skipping", repo_id)
        return RepoResult(repo_id=repo_id, language="", loc=_count_loc(repo_path))

    run = Run(id=str(uuid.uuid4()), repo_id=repo_id, status=RunStatus.PENDING)
    await insert_run(run)

    language = _language_for(repo_path)
    result = RepoResult(
        repo_id=repo_id,
        language=language,
        loc=_count_loc(repo_path),
        truth=[_truth_to_dict(t) for t in truth],
    )

    scan_start = time.monotonic()
    findings = await _run_hunter(run.id, repo_path, skip_llm=skip_llm)
    result.scan_wallclock_s = time.monotonic() - scan_start

    reported = _to_reported(findings)
    match_result = match_findings(reported, truth)
    truth_to_finding = match_result.truth_to_finding
    finding_to_truth = match_result.finding_to_truth

    finding_lookup = {f.id: f for f in findings}
    duplicate_ids = set(match_result.duplicate_findings)
    for r in reported:
        match = next(
            (m for m in match_result.matches if m.finding_id == r.id),
            None,
        )
        original = finding_lookup[r.id]
        severity = (
            original.severity.value
            if hasattr(original.severity, "value")
            else str(original.severity)
        )
        result.findings.append(
            FindingRow(
                finding_id=r.id,
                scanner=r.scanner,
                rule_id=r.rule_id,
                severity=severity,
                file_path=r.file_path,
                start_line=r.start_line,
                end_line=r.end_line,
                confidence=original.confidence,
                matched_truth_id=match.truth_id if match else None,
                match_reason=match.reason if match else None,
                match_distance=match.line_distance if match else None,
                is_duplicate=r.id in duplicate_ids,
            )
        )
    result.unmatched_finding_ids = list(match_result.unmatched_findings)

    # Build one pipeline row per truth entry so later metrics have total truth
    # coverage regardless of detection outcome.
    for t in truth:
        finding_id = truth_to_finding.get(t.id)
        row = PipelineRow(
            truth_id=t.id,
            detected=finding_id is not None,
            finding_id=finding_id,
            scan_time_s=result.scan_wallclock_s,
        )
        if finding_id is not None:
            detecting_finding = finding_lookup[finding_id]
            row.detected_by = detecting_finding.scanner
        result.pipeline.append(row)

    if not hunter_only:
        await _drive_patch_and_verify(result, repo_path, finding_lookup, finding_to_truth)

    result.hunter_metrics = _compute_hunter_metrics(result.findings, truth, match_result)
    result.surgeon_metrics = _compute_surgeon_metrics(result.pipeline)
    result.critic_metrics = _compute_critic_metrics(result.pipeline)
    result.end_to_end = _compute_end_to_end(result.pipeline, truth_count=len(truth))
    result.timings = _compute_timings(result.pipeline, result.scan_wallclock_s)

    return result


async def _drive_patch_and_verify(
    result: RepoResult,
    repo_path: Path,
    finding_lookup: dict,  # noqa: ANN001
    finding_to_truth: dict[str, str],
) -> None:
    """Run Surgeon+Critic and Verifier for every detected truth-matched finding."""
    detected_rows = [r for r in result.pipeline if r.detected and r.finding_id]
    log.info(
        "  driving Surgeon+Critic+Verifier for %d detected findings",
        len(detected_rows),
    )

    for row in detected_rows:
        finding_id = row.finding_id
        assert finding_id is not None

        t0 = time.monotonic()
        patch_outcome = await _run_patch_pipeline(finding_id, repo_path)
        row.patch_time_s = time.monotonic() - t0
        if patch_outcome is None:
            continue
        patch_id, attempt, approved = patch_outcome
        row.patch_id = patch_id
        row.patch_attempt = attempt
        row.critic_approved = approved

        if not approved:
            continue

        v0 = time.monotonic()
        verify_outcome = await _run_verifier(patch_id, finding_id, repo_path)
        row.verify_time_s = time.monotonic() - v0
        if verify_outcome is None:
            continue
        clean, details = verify_outcome
        row.verification_clean = clean
        row.verification_details = details


def _language_for(repo_path: Path) -> str:
    if (repo_path / "package.json").exists():
        return "javascript"
    if (repo_path / "requirements.txt").exists():
        return "python"
    return "unknown"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


CURATED = ["vibe-todo-app", "vibe-notes-api", "vibe-file-share", "vibe-auth-service"]


async def _run(args: argparse.Namespace) -> int:
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    eval_db_path = out_dir / "eval.db"

    _init_backend_for(eval_db_path)
    await _new_eval_db(eval_db_path)

    selected = args.repos or CURATED
    missing = [r for r in selected if r not in CURATED]
    if missing:
        log.error("Unknown repo(s): %s", ", ".join(missing))
        return 2

    demo_base = REPO_ROOT / "demo-repos"
    results: list[RepoResult] = []
    for repo_id in selected:
        repo_path = demo_base / repo_id
        if not repo_path.is_dir():
            log.error("demo-repo not found: %s", repo_path)
            continue
        res = await _eval_repo(
            repo_id,
            repo_path,
            hunter_only=args.hunter_only,
            skip_llm=args.skip_llm_review,
        )
        results.append(res)

    aggregate = _aggregate(results)

    _write_raw(out_dir, results)
    report_md = render_markdown(results, aggregate, generated_at=datetime.now(timezone.utc))
    (out_dir / "EVAL.md").write_text(report_md)

    summary = render_summary_json(results, aggregate)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    _print_console_summary(results, aggregate)
    log.info("Artifacts written to %s", out_dir)
    return 0


def _aggregate(results: list[RepoResult]) -> dict:
    """Roll per-repo numbers up into a global summary."""
    truth_total = sum(len(r.truth) for r in results)
    detected = sum(r.end_to_end.get("detected", 0) for r in results)
    patched = sum(r.end_to_end.get("patched", 0) for r in results)
    approved = sum(r.end_to_end.get("approved", 0) for r in results)
    verified = sum(r.end_to_end.get("verified_clean", 0) for r in results)

    def _sum_field(scanner_key: str, field_name: str) -> int:
        return sum(r.hunter_metrics.get(scanner_key, {}).get(field_name, 0) for r in results)

    def _metric_block(scanner_key: str) -> dict:
        tp = _sum_field(scanner_key, "tp")
        fp = _sum_field(scanner_key, "fp")
        fn = _sum_field(scanner_key, "fn")
        bonus = _sum_field(scanner_key, "bonus")
        expected = _sum_field(scanner_key, "expected")
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        return {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "bonus": bonus,
            "expected": expected,
            "precision": _pct_fmt(precision),
            "recall": _pct_fmt(recall),
            "f1": _pct_fmt(f1),
        }

    llm_only_total = sum(
        r.hunter_metrics.get("llm_only_contribution_count", 0) for r in results
    )

    surgeon_attempted = sum(r.surgeon_metrics.get("patches_attempted", 0) for r in results)
    surgeon_apply_numer = sum(
        int(r.surgeon_metrics.get("patches_attempted", 0) * r.surgeon_metrics.get("apply_rate", 0.0))
        for r in results
    )

    verdicts = sum(r.critic_metrics.get("verdicts", 0) for r in results)
    approved_cnt = sum(r.critic_metrics.get("approved", 0) for r in results)
    rejected_cnt = sum(r.critic_metrics.get("rejected", 0) for r in results)
    approved_and_clean = sum(
        1
        for r in results
        for p in r.pipeline
        if p.critic_approved and p.verification_clean is True
    )
    approved_and_dirty = sum(
        1
        for r in results
        for p in r.pipeline
        if p.critic_approved and p.verification_clean is False
    )

    return {
        "truth_total": truth_total,
        "loc_total": sum(r.loc for r in results),
        "hunter": {
            "semgrep": _metric_block("semgrep"),
            "llm": _metric_block("llm"),
            "combined": _metric_block("combined"),
            "llm_only_contribution_count": llm_only_total,
        },
        "surgeon": {
            "patches_attempted": surgeon_attempted,
            "patches_applied": surgeon_apply_numer,
            "apply_rate": _pct_fmt(_safe_div(surgeon_apply_numer, surgeon_attempted)),
        },
        "critic": {
            "verdicts": verdicts,
            "approved": approved_cnt,
            "rejected": rejected_cnt,
            "approval_rate": _pct_fmt(_safe_div(approved_cnt, verdicts)),
            "agreement_with_verifier": _pct_fmt(
                _safe_div(approved_and_clean, approved_and_clean + approved_and_dirty)
            ),
            "false_accept_rate": _pct_fmt(
                _safe_div(approved_and_dirty, approved_and_clean + approved_and_dirty)
            ),
        },
        "end_to_end": {
            "detected": detected,
            "patched": patched,
            "approved": approved,
            "verified_clean": verified,
            "detection_rate": _pct_fmt(_safe_div(detected, truth_total)),
            "fix_rate": _pct_fmt(_safe_div(verified, truth_total)),
        },
    }


def _write_raw(out_dir: Path, results: list[RepoResult]) -> None:
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        payload = {
            "repo_id": r.repo_id,
            "language": r.language,
            "loc": r.loc,
            "truth": r.truth,
            "findings": [asdict(x) for x in r.findings],
            "pipeline": [asdict(x) for x in r.pipeline],
            "unmatched_finding_ids": r.unmatched_finding_ids,
            "scan_wallclock_s": r.scan_wallclock_s,
            "hunter_metrics": r.hunter_metrics,
            "surgeon_metrics": r.surgeon_metrics,
            "critic_metrics": r.critic_metrics,
            "end_to_end": r.end_to_end,
            "timings": r.timings,
        }
        (raw_dir / f"{r.repo_id}.json").write_text(json.dumps(payload, indent=2))


def _print_console_summary(results: list[RepoResult], aggregate: dict) -> None:
    log.info("")
    log.info("=== Summary ===")
    for r in results:
        h = r.hunter_metrics.get("combined", {})
        ete = r.end_to_end
        log.info(
            "%-20s  truth=%d  detected=%d  P=%.2f R=%.2f F1=%.2f  fix=%d/%d",
            r.repo_id,
            len(r.truth),
            ete.get("detected", 0),
            h.get("precision", 0.0),
            h.get("recall", 0.0),
            h.get("f1", 0.0),
            ete.get("verified_clean", 0),
            len(r.truth),
        )
    agg_h = aggregate["hunter"]["combined"]
    ete = aggregate["end_to_end"]
    log.info("")
    log.info(
        "AGGREGATE  truth=%d  detected=%d  P=%.2f R=%.2f F1=%.2f  fix=%d/%d  llm-only=%d",
        aggregate["truth_total"],
        ete["detected"],
        agg_h["precision"],
        agg_h["recall"],
        agg_h["f1"],
        ete["verified_clean"],
        aggregate["truth_total"],
        aggregate["hunter"]["llm_only_contribution_count"],
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vigil-eval",
        description="Run Vigil end-to-end against curated demo repos and report metrics.",
    )
    parser.add_argument(
        "--repos",
        nargs="+",
        metavar="REPO_ID",
        help=f"Subset of curated repos to evaluate. Default: all of {', '.join(CURATED)}",
    )
    parser.add_argument(
        "--hunter-only",
        action="store_true",
        help="Skip Surgeon/Critic/Verifier. Fastest; only Hunter metrics are produced.",
    )
    parser.add_argument(
        "--skip-llm-review",
        action="store_true",
        help="Run only Phase 1 of Hunter (Semgrep). No Anthropic calls during scanning.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Artifact output directory. Defaults to eval-artifacts/<iso-ts>/",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose logging."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.out is None:
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        args.out = REPO_ROOT / "eval-artifacts" / ts

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
