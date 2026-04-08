"""Hunter module — invokes the Semgrep CLI and returns raw JSON output."""

import asyncio
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SEMGREP_TIMEOUT_SECONDS = 120


class ScanError(Exception):
    """Raised when a Semgrep scan fails to execute."""


async def run_semgrep(repo_path: str | Path) -> dict:
    """Run ``semgrep scan --config auto --json`` on *repo_path* and return the
    parsed JSON output.

    Raises :class:`ScanError` if semgrep is not installed, times out, or
    returns an unparseable result.
    """
    repo_path = str(repo_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            "semgrep", "scan",
            "--config", "auto",
            "--json",
            "--no-git-ignore",
            repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=SEMGREP_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        raise ScanError(
            "semgrep is not installed or not on PATH. "
            "Install it with: pip install semgrep"
        )
    except asyncio.TimeoutError:
        proc.kill()  # type: ignore[union-attr]
        raise ScanError(
            f"semgrep timed out after {SEMGREP_TIMEOUT_SECONDS}s "
            f"scanning {repo_path}"
        )

    # Semgrep exits 0 on clean scan, 1 when findings exist — both are valid.
    # Exit code 2+ indicates a real error.
    if proc.returncode is not None and proc.returncode >= 2:
        raise ScanError(
            f"semgrep exited with code {proc.returncode}: "
            f"{stderr.decode(errors='replace').strip()}"
        )

    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ScanError(f"semgrep produced invalid JSON: {exc}")

    if "results" not in raw:
        raise ScanError(
            "semgrep JSON missing 'results' key — unexpected output format"
        )

    log.info(
        "semgrep scan complete: %d results, %d errors",
        len(raw.get("results", [])),
        len(raw.get("errors", [])),
    )
    return raw
