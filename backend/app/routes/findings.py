"""Findings explorer — list and inspect vulnerability findings for a run."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..db import get_finding, get_findings_by_run, get_run
from ..models.finding import SeverityLevel

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
