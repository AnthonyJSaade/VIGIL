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

# Safety net mirroring ``run_semgrep``'s timeout pattern. ``--batch`` should
# make ``patch`` exit immediately on any ambiguity, but a bounded wait keeps
# the background verification task deterministic even if the subprocess
# misbehaves for any other reason.
PATCH_TIMEOUT_SECONDS = 30


class PatchApplyError(Exception):
    """Raised when a unified diff cannot be applied cleanly to a sandbox copy."""

    def __init__(self, message: str, diagnostics: str = "") -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


def _extract_target_paths(diff: str) -> list[str]:
    """Return the list of relative paths touched by *diff*.

    Parses ``+++ b/path`` (``-p1`` style) and ``+++ path`` (``-p0`` style)
    headers. Skips the ``/dev/null`` sentinel used for additions. Preserves
    first-seen order and deduplicates.
    """
    seen: dict[str, None] = {}
    for line in diff.splitlines():
        if not line.startswith("+++ "):
            continue
        raw = line[4:].strip()
        if not raw or raw == "/dev/null":
            continue
        # Strip a trailing tab/timestamp if present.
        raw = raw.split("\t", 1)[0].strip()
        if raw.startswith("b/"):
            raw = raw[2:]
        elif raw.startswith("./"):
            raw = raw[2:]
        raw = raw.lstrip("/")
        if raw and raw not in seen:
            seen[raw] = None
    return list(seen.keys())


async def apply_patch_in_temp(
    patch_diff: str,
    repo_path: Path,
) -> tuple[dict[str, str], str]:
    """Apply *patch_diff* to a temp copy of *repo_path* and return patched files.

    Returns ``({relative_path: new_text}, diagnostics)`` where the dict holds
    the post-patch contents of every file touched by the diff, and
    ``diagnostics`` is the combined `patch` output (usually empty on success).

    Raises :class:`PatchApplyError` if the diff cannot be applied or if the
    diff does not reference any recognizable file paths.
    """
    targets = _extract_target_paths(patch_diff)
    if not targets:
        raise PatchApplyError(
            "Could not identify any target files in the patch diff.",
        )

    sandbox_dir = Path(tempfile.mkdtemp(prefix="vigil-apply-"))
    sandbox_repo = sandbox_dir / "repo"

    try:
        shutil.copytree(repo_path, sandbox_repo)
        applied, diagnostics = await _apply_diff(sandbox_repo, patch_diff)
        if not applied:
            raise PatchApplyError(
                "Patch failed to apply cleanly to the sandbox copy.",
                diagnostics=diagnostics,
            )

        patched: dict[str, str] = {}
        for rel in targets:
            sandbox_file = sandbox_repo / rel
            if not sandbox_file.is_file():
                raise PatchApplyError(
                    f"Patched file not found in sandbox: {rel}",
                    diagnostics=diagnostics,
                )
            patched[rel] = sandbox_file.read_text(errors="replace")

        return patched, diagnostics

    finally:
        shutil.rmtree(sandbox_dir, ignore_errors=True)


async def _run_patch(sandbox_path: Path, diff: str, strip: int) -> tuple[int, str]:
    """Invoke ``patch`` inside *sandbox_path* non-interactively.

    ``--batch`` makes ``patch`` non-interactive: on any ambiguity (missing
    target file, malformed hunk, reversed patch) it exits non-zero instead of
    prompting on ``/dev/tty`` and hanging the background verification task.
    The surrounding ``asyncio.wait_for`` is a belt-and-suspenders timeout
    mirroring the one in :func:`run_semgrep`.

    Returns ``(returncode, combined_output)`` where the output merges stdout
    and stderr so the caller can surface the real ``patch`` diagnostics.
    """
    proc = await asyncio.create_subprocess_exec(
        "patch", f"-p{strip}", "--batch", "--no-backup-if-mismatch", "-F", "3",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(sandbox_path),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=diff.encode()),
            timeout=PATCH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=2.0)
        except Exception:
            stdout, stderr = b"", b""
        combined = (
            stdout.decode(errors="replace")
            + stderr.decode(errors="replace")
            + f"\npatch subprocess killed after {PATCH_TIMEOUT_SECONDS}s timeout"
        ).strip()
        return 124, combined

    combined = (stdout.decode(errors="replace") + stderr.decode(errors="replace")).strip()
    return proc.returncode or 0, combined


async def _apply_diff(sandbox_path: Path, diff: str) -> tuple[bool, str]:
    """Apply a unified diff inside the sandbox using ``patch`` with fuzz.

    Tries ``-p1`` first (standard ``a/path`` ``b/path`` layout) and falls back
    to ``-p0`` when the LLM omitted the ``a/ b/`` prefix. Returns
    ``(applied, diagnostics)`` — ``diagnostics`` is empty on success and
    contains the combined stdout/stderr on failure so it can be shown in the
    verification report.
    """
    rc, out = await _run_patch(sandbox_path, diff, strip=1)
    if rc == 0:
        log.info("Patch applied cleanly with -p1: %s", out)
        return True, ""

    log.warning("patch -p1 failed (exit %d): %s", rc, out)

    rc0, out0 = await _run_patch(sandbox_path, diff, strip=0)
    if rc0 == 0:
        log.info("Patch applied cleanly with -p0 fallback: %s", out0)
        return True, ""

    log.warning("patch -p0 fallback also failed (exit %d): %s", rc0, out0)
    combined = f"-p1 attempt:\n{out}\n\n-p0 attempt:\n{out0}".strip()
    return False, combined


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

        patch_applied, patch_stderr = await _apply_diff(sandbox_repo, patch.diff)
        if not patch_applied:
            details = "Patch failed to apply cleanly to the sandbox copy."
            if patch_stderr:
                details = f"{details}\n\n{patch_stderr}"
            return VerificationReport(
                id=str(uuid.uuid4()),
                patch_id=patch.id,
                scanner_rerun_clean=False,
                tests_passed=None,
                details=details,
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
