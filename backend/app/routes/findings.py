"""Findings explorer — list, inspect, and trigger patch pipeline for findings."""

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from ..agents.orchestrator import run_patch_review_loop
from ..config import settings
from ..db import get_finding, get_findings_by_run, get_run, get_patches_by_finding, get_verdict_by_patch
from ..models.finding import SeverityLevel
from ..models.trace import AgentRole, TraceAction
from ..scanner.source import read_source_lines
from ..streaming.sse import bus
from .repos import CURATED_REPOS

log = logging.getLogger(__name__)

router = APIRouter(tags=["findings"])


class FindingSummary(BaseModel):
    id: str
    run_id: str
    scanner: str
    rule_id: str
    severity: str
    message: str
    file_path: str
    start_line: int
    end_line: int
    confidence: float
    created_at: str


class FindingDetail(FindingSummary):
    snippet: str
    metadata: dict


def _to_summary(f) -> FindingSummary:
    return FindingSummary(
        id=f.id, run_id=f.run_id, scanner=f.scanner, rule_id=f.rule_id,
        severity=f.severity.value, message=f.message, file_path=f.file_path,
        start_line=f.start_line, end_line=f.end_line, confidence=f.confidence,
        created_at=f.created_at.isoformat(),
    )


def _to_detail(f) -> FindingDetail:
    return FindingDetail(
        id=f.id, run_id=f.run_id, scanner=f.scanner, rule_id=f.rule_id,
        severity=f.severity.value, message=f.message, file_path=f.file_path,
        start_line=f.start_line, end_line=f.end_line, confidence=f.confidence,
        created_at=f.created_at.isoformat(), snippet=f.snippet,
        metadata=f.metadata,
    )


@router.get("/api/runs/{run_id}/findings", response_model=list[FindingSummary])
async def list_findings(
    run_id: str,
    severity: SeverityLevel | None = Query(None, description="Filter by severity level"),
    scanner: str | None = Query(None, description="Filter by scanner (semgrep, claude-review)"),
) -> list[FindingSummary]:
    run = await get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    findings = await get_findings_by_run(run_id)

    if severity is not None:
        findings = [f for f in findings if f.severity == severity]
    if scanner is not None:
        findings = [f for f in findings if f.scanner == scanner]

    return [_to_summary(f) for f in findings]


@router.get("/api/findings/{finding_id}", response_model=FindingDetail)
async def get_finding_detail(finding_id: str) -> FindingDetail:
    finding = await get_finding(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    # Safety net: historical findings may have an empty snippet (LLM path
    # mismatch) or stale non-code text (Semgrep rule metadata). If we can
    # resolve the repo on disk, prefer real source lines. We don't persist
    # the enriched snippet back to the DB — this endpoint stays side-effect-free.
    run = await get_run(finding.run_id)
    repo = next((r for r in CURATED_REPOS if r.id == run.repo_id), None) if run else None
    if repo is not None:
        repo_path = Path(settings.demo_repos_path) / repo.id
        real = read_source_lines(repo_path, finding.file_path, finding.start_line, finding.end_line)
        if real:
            finding.snippet = real

    return _to_detail(finding)


# ---------------------------------------------------------------------------
# Patch pipeline (Surgeon-Critic feedback loop)
# ---------------------------------------------------------------------------

class PatchView(BaseModel):
    id: str
    finding_id: str
    diff: str
    explanation: str
    model_used: str
    attempt: int
    prior_concerns: list[str] | None
    created_at: str


class VerdictView(BaseModel):
    id: str
    patch_id: str
    approved: bool
    reasoning: str
    concerns: list[str]
    model_used: str
    created_at: str


class PatchWithVerdict(BaseModel):
    """Paired patch + verdict. ``verdict`` is ``null`` while the Critic is still
    reviewing the patch, so the UI can show a loading state correctly."""

    patch: PatchView
    verdict: VerdictView | None


class PatchTriggerResponse(BaseModel):
    status: str
    finding_id: str
    message: str


async def _run_patch_pipeline(
    finding_id: str,
    repo_path: str,
    starting_attempt: int = 1,
) -> None:
    """Background task: run the Surgeon-Critic loop for a finding."""
    try:
        await run_patch_review_loop(finding_id, Path(repo_path), starting_attempt=starting_attempt)
    except Exception as exc:
        log.exception("Patch pipeline failed for finding %s: %s", finding_id, exc)
        finding = await get_finding(finding_id)
        if finding:
            await bus.publish(finding.run_id, AgentRole.SURGEON, TraceAction.PATCH_PROPOSED, {
                "finding_id": finding_id,
                "status": "error",
                "error": str(exc),
            })


@router.post("/api/findings/{finding_id}/patch", response_model=PatchTriggerResponse, status_code=202)
async def trigger_patch(
    finding_id: str,
    background_tasks: BackgroundTasks,
    force: bool = Query(False, description="Run the Surgeon-Critic loop again even if prior attempts exist"),
) -> PatchTriggerResponse:
    finding = await get_finding(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    existing_patches = await get_patches_by_finding(finding_id)
    if existing_patches and not force:
        raise HTTPException(
            status_code=409,
            detail="Patch pipeline already ran for this finding",
        )

    starting_attempt = (
        max((p.attempt for p in existing_patches), default=0) + 1
        if existing_patches
        else 1
    )

    run = await get_run(finding.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    repo = next((r for r in CURATED_REPOS if r.id == run.repo_id), None)
    if repo is None:
        raise HTTPException(status_code=404, detail="Unknown repo for this run")

    repo_path = settings.demo_repos_path / repo.id
    if not repo_path.exists():
        raise HTTPException(status_code=404, detail="Demo repo directory not found")

    background_tasks.add_task(_run_patch_pipeline, finding_id, str(repo_path), starting_attempt)

    return PatchTriggerResponse(
        status="started",
        finding_id=finding_id,
        message="Surgeon-Critic pipeline started. Watch the SSE stream for updates.",
    )


@router.get("/api/findings/{finding_id}/patches", response_model=list[PatchWithVerdict])
async def list_patches(finding_id: str) -> list[PatchWithVerdict]:
    finding = await get_finding(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    patches = await get_patches_by_finding(finding_id)
    results: list[PatchWithVerdict] = []
    for p in patches:
        verdict = await get_verdict_by_patch(p.id)
        patch_view = PatchView(
            id=p.id,
            finding_id=p.finding_id,
            diff=p.diff,
            explanation=p.explanation,
            model_used=p.model_used,
            attempt=p.attempt,
            prior_concerns=p.prior_concerns,
            created_at=p.created_at.isoformat(),
        )
        verdict_view = (
            VerdictView(
                id=verdict.id,
                patch_id=verdict.patch_id,
                approved=verdict.approved,
                reasoning=verdict.reasoning,
                concerns=verdict.concerns,
                model_used=verdict.model_used,
                created_at=verdict.created_at.isoformat(),
            )
            if verdict is not None
            else None
        )
        results.append(PatchWithVerdict(patch=patch_view, verdict=verdict_view))
    return results
