"""Findings explorer — list, inspect, and trigger patch pipeline for findings."""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from ..agents.orchestrator import run_patch_review_loop
from ..config import settings
from ..db import get_finding, get_findings_by_run, get_run, get_patches_by_finding
from ..models.finding import SeverityLevel
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
    return _to_detail(finding)


# ---------------------------------------------------------------------------
# Patch pipeline (Surgeon-Critic feedback loop)
# ---------------------------------------------------------------------------

class PatchResult(BaseModel):
    patch_id: str
    finding_id: str
    diff: str
    explanation: str
    attempt: int
    approved: bool
    reasoning: str
    concerns: list[str]


class PatchTriggerResponse(BaseModel):
    status: str
    finding_id: str
    message: str


async def _run_patch_pipeline(finding_id: str, repo_path: str) -> None:
    """Background task: run the Surgeon-Critic loop for a finding."""
    from pathlib import Path
    try:
        await run_patch_review_loop(finding_id, Path(repo_path))
    except Exception as exc:
        log.exception("Patch pipeline failed for finding %s: %s", finding_id, exc)


@router.post("/api/findings/{finding_id}/patch", response_model=PatchTriggerResponse, status_code=202)
async def trigger_patch(
    finding_id: str,
    background_tasks: BackgroundTasks,
) -> PatchTriggerResponse:
    finding = await get_finding(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    existing_patches = await get_patches_by_finding(finding_id)
    if existing_patches:
        raise HTTPException(
            status_code=409,
            detail="Patch pipeline already ran for this finding",
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

    background_tasks.add_task(_run_patch_pipeline, finding_id, str(repo_path))

    return PatchTriggerResponse(
        status="started",
        finding_id=finding_id,
        message="Surgeon-Critic pipeline started. Watch the SSE stream for updates.",
    )


@router.get("/api/findings/{finding_id}/patches", response_model=list[PatchResult])
async def list_patches(finding_id: str) -> list[PatchResult]:
    finding = await get_finding(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    from ..db import get_verdict_by_patch

    patches = await get_patches_by_finding(finding_id)
    results = []
    for p in patches:
        verdict = await get_verdict_by_patch(p.id)
        results.append(PatchResult(
            patch_id=p.id,
            finding_id=p.finding_id,
            diff=p.diff,
            explanation=p.explanation,
            attempt=p.attempt,
            approved=verdict.approved if verdict else False,
            reasoning=verdict.reasoning if verdict else "Pending review",
            concerns=verdict.concerns if verdict else [],
        ))
    return results
