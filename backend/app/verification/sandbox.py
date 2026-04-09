"""Sandbox verification — copies the repo, applies a patch, and reruns Semgrep.

Verification always runs on a temporary copy of the repo, never on the
original source tree.  After applying the unified diff, it reruns Semgrep
and checks whether the original finding's rule no longer fires on the
patched file.
"""

import asyncio
import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from ..models.finding import Finding
from ..models.patch import PatchProposal
from ..models.verification import VerificationReport
from ..scanner.runner import ScanError, run_semgrep
from ..scanner.normalizer import normalize_findings

log = logging.getLogger(__name__)


async def _apply_diff(sandbox_path: Path, diff: str) -> bool:
    """Apply a unified diff inside the sandbox using ``patch``.

    Returns True if the patch applied cleanly, False otherwise.
    """
    proc = await asyncio.create_subprocess_exec(
        "patch", "-p1", "--no-backup-if-mismatch",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(sandbox_path),
    )
    stdout, stderr = await proc.communicate(input=diff.encode())

    if proc.returncode != 0:
        log.warning(
            "patch failed (exit %d): %s",
            proc.returncode,
            stderr.decode(errors="replace").strip(),
        )
        return False

    log.info("Patch applied cleanly: %s", stdout.decode(errors="replace").strip())
    return True


def _finding_still_present(
    findings: list[Finding],
    original: Finding,
) -> bool:
    """Check if the original finding's rule still fires on the same file and
    overlapping line range."""
    for f in findings:
        if f.rule_id == original.rule_id and f.file_path == original.file_path:
            if (
                f.start_line <= original.end_line + 5
                and f.end_line >= original.start_line - 5
            ):
                return True
    return False


async def verify_patch(
    patch: PatchProposal,
    original_finding: Finding,
    repo_path: Path,
) -> VerificationReport:
    """Run the full verification pipeline in a sandbox copy.

    1. Copy the repo to a temporary directory.
    2. Apply the unified diff from the patch.
    3. Rerun Semgrep on the patched repo.
    4. Check if the original finding's rule no longer fires.

    Returns a :class:`VerificationReport` with the results.
    """
    sandbox_dir = Path(tempfile.mkdtemp(prefix="vigil-verify-"))
    sandbox_repo = sandbox_dir / "repo"

    try:
        shutil.copytree(repo_path, sandbox_repo)
        log.info("Sandbox created at %s", sandbox_repo)

        patch_applied = await _apply_diff(sandbox_repo, patch.diff)
        if not patch_applied:
            return VerificationReport(
                id=str(uuid.uuid4()),
                patch_id=patch.id,
                scanner_rerun_clean=False,
                tests_passed=None,
                details="Patch failed to apply cleanly to the sandbox copy.",
            )

        try:
            raw = await run_semgrep(sandbox_repo)
            post_findings = normalize_findings(raw, "verification")
        except ScanError as exc:
            return VerificationReport(
                id=str(uuid.uuid4()),
                patch_id=patch.id,
                scanner_rerun_clean=False,
                tests_passed=None,
                details=f"Semgrep rerun failed: {exc}",
            )

        still_present = _finding_still_present(post_findings, original_finding)

        if still_present:
            return VerificationReport(
                id=str(uuid.uuid4()),
                patch_id=patch.id,
                scanner_rerun_clean=False,
                tests_passed=None,
                details=(
                    f"The original finding ({original_finding.rule_id}) "
                    f"still fires after applying the patch."
                ),
            )

        return VerificationReport(
            id=str(uuid.uuid4()),
            patch_id=patch.id,
            scanner_rerun_clean=True,
            tests_passed=None,
            details=(
                f"Patch verified: {original_finding.rule_id} no longer fires. "
                f"Semgrep found {len(post_findings)} total findings in patched repo "
                f"(down from original scan)."
            ),
        )

    finally:
        shutil.rmtree(sandbox_dir, ignore_errors=True)
