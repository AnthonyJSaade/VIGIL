"""Patch verification — run an approved patch through the sandbox verifier."""

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from ..config import settings
from ..db import (
    delete_verification_by_patch,
    get_finding,
    get_patch,
    get_run,
    get_verdict_by_patch,
    get_verification_by_patch,
    insert_verification,
)
from ..models.trace import AgentRole, TraceAction
from ..streaming.sse import bus
from ..verification.sandbox import verify_patch
from .repos import CURATED_REPOS

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patches", tags=["patches"])


class VerificationResponse(BaseModel):
    patch_id: str
    scanner_rerun_clean: bool
    tests_passed: bool | None
    details: str


class VerifyTriggerResponse(BaseModel):
    status: str
    patch_id: str
    message: str


async def _run_verification(patch_id: str, repo_path: str) -> None:
    """Background task: run sandbox verification for a patch."""
    patch = await get_patch(patch_id)
    if patch is None:
        log.error("Patch %s disappeared before verification", patch_id)
        return

    finding = await get_finding(patch.finding_id)
    if finding is None:
        log.error("Finding %s disappeared before verification", patch.finding_id)
        return

    run_id = finding.run_id

    try:
        await bus.publish(run_id, AgentRole.VERIFIER, TraceAction.VERIFICATION_STARTED, {
            "patch_id": patch_id,
        })

        report = await verify_patch(patch, finding, Path(repo_path))
        await insert_verification(report)

        await bus.publish(run_id, AgentRole.VERIFIER, TraceAction.VERIFICATION_COMPLETED, {
            "patch_id": patch_id,
            "verification_id": report.id,
            "scanner_rerun_clean": report.scanner_rerun_clean,
            "details": report.details,
        })
        bus.close(run_id)
    except Exception as exc:
        log.exception("Verification failed for patch %s: %s", patch_id, exc)
        await bus.publish(run_id, AgentRole.VERIFIER, TraceAction.VERIFICATION_COMPLETED, {
            "patch_id": patch_id,
            "error": str(exc),
        })
        bus.close(run_id)


@router.post("/{patch_id}/verify", response_model=VerifyTriggerResponse, status_code=202)
async def trigger_verification(
    patch_id: str,
    background_tasks: BackgroundTasks,
    force: bool = Query(False, description="Re-run verification even if a prior report exists"),
) -> VerifyTriggerResponse:
    patch = await get_patch(patch_id)
    if patch is None:
        raise HTTPException(status_code=404, detail="Patch not found")

    verdict = await get_verdict_by_patch(patch_id)
    if verdict is None or not verdict.approved:
        raise HTTPException(
            status_code=400,
            detail="Patch must be approved by the Critic before verification",
        )

    existing = await get_verification_by_patch(patch_id)
    if existing is not None:
        if not force:
            raise HTTPException(
                status_code=409,
                detail="Verification already ran for this patch",
            )
        await delete_verification_by_patch(patch_id)

    finding = await get_finding(patch.finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    run = await get_run(finding.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    repo = next((r for r in CURATED_REPOS if r.id == run.repo_id), None)
    if repo is None:
        raise HTTPException(status_code=404, detail="Unknown repo for this run")

    repo_path = settings.demo_repos_path / repo.id
    if not repo_path.exists():
        raise HTTPException(status_code=404, detail="Demo repo directory not found")

    background_tasks.add_task(_run_verification, patch_id, str(repo_path))

    return VerifyTriggerResponse(
        status="started",
        patch_id=patch_id,
        message="Sandbox verification started. Watch the SSE stream for updates.",
    )


@router.get("/{patch_id}/verification", response_model=VerificationResponse)
async def get_verification_result(patch_id: str) -> VerificationResponse:
    patch = await get_patch(patch_id)
    if patch is None:
        raise HTTPException(status_code=404, detail="Patch not found")

    report = await get_verification_by_patch(patch_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Verification not yet completed")

    return VerificationResponse(
        patch_id=patch_id,
        scanner_rerun_clean=report.scanner_rerun_clean,
        tests_passed=report.tests_passed,
        details=report.details,
    )
