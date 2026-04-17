"""Patch verification — run an approved patch through the sandbox verifier."""

import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import Response
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
from ..verification.sandbox import PatchApplyError, apply_patch_in_temp, verify_patch
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


# ---------------------------------------------------------------------------
# Post-verification actions: download / apply
# ---------------------------------------------------------------------------

class ApplyResponse(BaseModel):
    patch_id: str
    applied_files: list[str]
    backups: list[str]


async def _resolve_verified_patch_repo(patch_id: str) -> tuple[Path, str, object]:
    """Load a patch that has already passed a clean verification.

    Returns ``(repo_path, primary_file_path, patch)``. Raises HTTPException
    with the appropriate status code on any gating failure.
    """
    patch = await get_patch(patch_id)
    if patch is None:
        raise HTTPException(status_code=404, detail="Patch not found")

    verdict = await get_verdict_by_patch(patch_id)
    if verdict is None or not verdict.approved:
        raise HTTPException(status_code=400, detail="Patch is not approved by the Critic")

    report = await get_verification_by_patch(patch_id)
    if report is None:
        raise HTTPException(status_code=400, detail="Verify this patch before applying or downloading")
    if not report.scanner_rerun_clean:
        raise HTTPException(status_code=400, detail="Verification failed; apply is disabled")

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

    return repo_path, finding.file_path, patch


@router.get("/{patch_id}/patched-file")
async def download_patched_file(patch_id: str) -> Response:
    """Return the post-patch content of the file(s) touched by this patch.

    Single-file patches stream the raw file. Multi-file patches are bundled
    into a ZIP archive with the relative paths preserved.
    """
    repo_path, primary_file, patch = await _resolve_verified_patch_repo(patch_id)

    try:
        patched, _ = await apply_patch_in_temp(patch.diff, repo_path)
    except PatchApplyError as exc:
        detail = str(exc)
        if exc.diagnostics:
            detail = f"{detail}\n\n{exc.diagnostics}"
        raise HTTPException(status_code=422, detail=detail) from exc

    if len(patched) == 1:
        rel, content = next(iter(patched.items()))
        filename = Path(rel).name or "patched-file.txt"
        return Response(
            content=content.encode(),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, content in patched.items():
            zf.writestr(rel, content)
    bundle_name = f"patched-{Path(primary_file).stem or 'files'}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle_name}"'},
    )


@router.post("/{patch_id}/apply", response_model=ApplyResponse)
async def apply_patch_to_repo(patch_id: str) -> ApplyResponse:
    """Write the patched file(s) back to the curated demo repo.

    A timestamped backup is written next to each overwritten file before any
    writes happen, so the demo stays re-runnable.
    """
    repo_path, _, patch = await _resolve_verified_patch_repo(patch_id)

    try:
        patched, _ = await apply_patch_in_temp(patch.diff, repo_path)
    except PatchApplyError as exc:
        detail = str(exc)
        if exc.diagnostics:
            detail = f"{detail}\n\n{exc.diagnostics}"
        raise HTTPException(status_code=422, detail=detail) from exc

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")

    # Phase 1: write all backups so an error mid-loop can't leave the repo
    # partially overwritten without a recovery path.
    backups: list[str] = []
    for rel in patched:
        target = repo_path / rel
        if not target.is_file():
            raise HTTPException(
                status_code=422,
                detail=f"Cannot apply patch: original file missing at {rel}",
            )
        backup_path = target.with_name(f"{target.name}.vigil-backup-{ts}")
        if not backup_path.exists():
            backup_path.write_bytes(target.read_bytes())
        backups.append(str(backup_path.relative_to(settings.demo_repos_path)))

    # Phase 2: overwrite the originals.
    applied: list[str] = []
    for rel, new_content in patched.items():
        target = repo_path / rel
        target.write_text(new_content)
        applied.append(rel)

    log.info("Applied patch %s to %s (backups: %s)", patch_id, applied, backups)

    return ApplyResponse(patch_id=patch_id, applied_files=applied, backups=backups)
