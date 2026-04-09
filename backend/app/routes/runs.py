"""Run lifecycle — create an audit run and query its status."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..db import get_run, insert_run, update_run_status
from ..models import Run, RunStatus, AgentRole, TraceAction
from ..scanner.orchestrator import run_full_scan
from ..scanner.runner import ScanError
from ..streaming.sse import bus
from .repos import CURATED_REPOS

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])


class CreateRunRequest(BaseModel):
    repo_id: str


class RunSummary(BaseModel):
    id: str
    repo_id: str
    status: str
    finding_count: int
    created_at: str


async def _execute_scan(run_id: str, repo_path: Path) -> None:
    """Background task: run the full Hunter pipeline (Semgrep + LLM review)."""
    try:
        await update_run_status(run_id, RunStatus.SCANNING)

        findings = await run_full_scan(run_id, repo_path)

        await update_run_status(run_id, RunStatus.COMPLETED,
                                finding_count=len(findings))

    except ScanError as exc:
        log.error("scan failed for run %s: %s", run_id, exc)
        await update_run_status(run_id, RunStatus.FAILED)
        await bus.publish(run_id, AgentRole.HUNTER, TraceAction.SCAN_COMPLETED,
                          {"error": str(exc)})
        bus.close(run_id)
    except Exception as exc:
        log.exception("unexpected error during scan for run %s", run_id)
        await update_run_status(run_id, RunStatus.FAILED)
        await bus.publish(run_id, AgentRole.HUNTER, TraceAction.SCAN_COMPLETED,
                          {"error": str(exc)})
        bus.close(run_id)


@router.post("", response_model=RunSummary, status_code=201)
async def create_run(
    body: CreateRunRequest,
    background_tasks: BackgroundTasks,
) -> RunSummary:
    repo = next((r for r in CURATED_REPOS if r.id == body.repo_id), None)
    if repo is None:
        raise HTTPException(status_code=404, detail="Unknown repo_id")

    repo_path = settings.demo_repos_path / repo.id
    if not repo_path.exists():
        raise HTTPException(status_code=404,
                            detail=f"Demo repo directory not found: {repo_path}")

    run = Run(id=str(uuid.uuid4()), repo_id=body.repo_id)
    await insert_run(run)

    background_tasks.add_task(_execute_scan, run.id, repo_path)

    return RunSummary(
        id=run.id,
        repo_id=run.repo_id,
        status=run.status,
        finding_count=run.finding_count,
        created_at=run.created_at.isoformat(),
    )


@router.get("/{run_id}", response_model=RunSummary)
async def get_run_detail(run_id: str) -> RunSummary:
    run = await get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunSummary(
        id=run.id,
        repo_id=run.repo_id,
        status=run.status,
        finding_count=run.finding_count,
        created_at=run.created_at.isoformat(),
    )
