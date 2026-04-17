"""Surgeon-Critic feedback loop orchestrator.

Runs the Surgeon -> Critic pipeline with up to ``MAX_ATTEMPTS`` iterations.
On rejection, the Surgeon retries with the Critic's concerns appended.
All steps publish SSE events for real-time UI streaming.
"""

import logging
from pathlib import Path

from ..db import get_finding, insert_patch, insert_verdict
from ..models.critic import CriticVerdict
from ..models.finding import Finding
from ..models.patch import PatchProposal
from ..models.trace import AgentRole, TraceAction
from ..streaming.sse import bus
from .critic import review_patch
from .surgeon import propose_patch

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2


async def _read_source_from_repo(finding: Finding, repo_path: Path) -> str:
    """Read the source file from a known repo path."""
    candidate = repo_path / finding.file_path
    if not candidate.is_file():
        raise FileNotFoundError(f"Source file not found: {candidate}")
    return candidate.read_text(errors="replace")


async def run_patch_review_loop(
    finding_id: str,
    repo_path: Path,
    starting_attempt: int = 1,
) -> tuple[PatchProposal, CriticVerdict]:
    """Execute the Surgeon -> Critic feedback loop.

    1. Surgeon proposes a patch for the finding.
    2. Critic reviews the patch independently.
    3. If rejected and attempts remain, Surgeon retries with Critic's concerns.
    4. Returns the final (patch, verdict) pair.

    ``starting_attempt`` lets a user-triggered retry continue the numbering from
    previously stored attempts instead of resetting to 1.

    Publishes SSE events at each step for real-time UI updates.

    Raises:
        ValueError: If finding not found or API key missing.
        FileNotFoundError: If source file cannot be located.
    """
    finding = await get_finding(finding_id)
    if finding is None:
        raise ValueError(f"Finding {finding_id} not found")

    run_id = finding.run_id
    file_content = await _read_source_from_repo(finding, repo_path)

    prior_concerns: list[str] | None = None
    patch: PatchProposal | None = None
    verdict: CriticVerdict | None = None

    last_attempt = starting_attempt + MAX_ATTEMPTS - 1
    for attempt in range(starting_attempt, last_attempt + 1):
        # ── Surgeon proposes ────────────────────────────────────────
        await bus.publish(run_id, AgentRole.SURGEON, TraceAction.PATCH_PROPOSED, {
            "finding_id": finding_id,
            "attempt": attempt,
            "status": "thinking",
        })

        patch = await propose_patch(
            finding, file_content,
            prior_concerns=prior_concerns,
            attempt=attempt,
        )
        await insert_patch(patch)

        await bus.publish(run_id, AgentRole.SURGEON, TraceAction.PATCH_PROPOSED, {
            "finding_id": finding_id,
            "patch_id": patch.id,
            "attempt": attempt,
            "status": "complete",
        })

        # ── Critic reviews ──────────────────────────────────────────
        await bus.publish(run_id, AgentRole.CRITIC, TraceAction.REVIEW_STARTED, {
            "patch_id": patch.id,
            "attempt": attempt,
        })

        verdict = await review_patch(finding, patch, file_content)
        await insert_verdict(verdict)

        if verdict.approved:
            await bus.publish(run_id, AgentRole.CRITIC, TraceAction.REVIEW_APPROVED, {
                "patch_id": patch.id,
                "verdict_id": verdict.id,
            })
            break

        # Rejected — publish rejection event
        await bus.publish(run_id, AgentRole.CRITIC, TraceAction.REVIEW_REJECTED, {
            "patch_id": patch.id,
            "verdict_id": verdict.id,
            "concerns": verdict.concerns,
        })

        if attempt < last_attempt:
            prior_concerns = verdict.concerns
            await bus.publish(run_id, AgentRole.SURGEON, TraceAction.PATCH_RETRIED, {
                "finding_id": finding_id,
                "attempt": attempt + 1,
                "concerns": verdict.concerns,
            })

    assert patch is not None and verdict is not None
    return patch, verdict
