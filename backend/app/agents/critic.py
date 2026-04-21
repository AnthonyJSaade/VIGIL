"""Critic agent — independently reviews patches proposed by the Surgeon.

The Critic has NO access to the Surgeon's reasoning or explanation. It only
sees the original vulnerability, the proposed diff, and the source file.
This ensures an independent security review.
"""

import json
import logging
import uuid

import anthropic

from ..config import settings
from ..models.critic import CriticVerdict
from ..models.finding import Finding
from ..models.patch import PatchProposal

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the Critic — an independent security reviewer. Your job is to \
evaluate whether a proposed patch actually fixes the vulnerability without \
introducing new problems.

You have NOT seen the Surgeon's reasoning. You must evaluate the diff on its \
own merits.

Evaluation criteria:
1. Does the patch fix the stated vulnerability?
2. Does the patch introduce any new security issues?
3. Is the patch minimal — no unnecessary changes?
4. Does it use secure coding patterns (parameterized queries, allow-lists, \
proper escaping, env-based secrets)?
5. Could the patch break existing functionality?
6. Does it suppress a rule, remove auth, or widen trust boundaries instead \
of truly fixing the issue?

Return ONLY a JSON object with exactly these fields:
{
  "approved": <true or false>,
  "reasoning": "<2-3 sentence overall assessment>",
  "concerns": ["<specific concern 1>", "<specific concern 2>", ...]
}

If approved, "concerns" should be an empty array.
If rejected, "concerns" must list specific, actionable problems.

Do NOT wrap the JSON in markdown code fences. Return raw JSON only.
"""


def _build_user_prompt(
    finding: Finding,
    patch: PatchProposal,
    file_content: str,
) -> str:
    parts = [
        "## Original Vulnerability\n",
        f"**Rule**: {finding.rule_id}\n",
        f"**Severity**: {finding.severity.value}\n",
        f"**File**: {finding.file_path}\n",
        f"**Lines**: {finding.start_line}–{finding.end_line}\n",
        f"**Message**: {finding.message}\n",
        f"\n## Proposed Patch (attempt {patch.attempt})\n```diff\n{patch.diff}\n```\n",
        f"\n## Full Source File ({finding.file_path})\n```\n{file_content}\n```\n",
    ]
    return "\n".join(parts)


def _parse_response(raw_text: str) -> tuple[bool, str, list[str]]:
    """Extract approved, reasoning, and concerns from Claude's JSON response."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    data = json.loads(text)
    return data["approved"], data["reasoning"], data.get("concerns", [])


async def review_patch(
    finding: Finding,
    patch: PatchProposal,
    file_content: str,
) -> CriticVerdict:
    """Call Claude to independently review a proposed patch.

    Args:
        finding: The original vulnerability the patch targets.
        patch: The Surgeon's proposed patch (only the diff is shown to Claude).
        file_content: Full content of the affected source file.

    Returns:
        A :class:`CriticVerdict` with the approval decision and reasoning.

    Raises:
        ValueError: If the API key is missing or Claude returns unparseable output.
    """
    if not settings.anthropic_api_key:
        raise ValueError("VIGIL_ANTHROPIC_API_KEY is not configured")

    user_prompt = _build_user_prompt(finding, patch, file_content)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.critic_model,
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw_text = response.content[0].text

    try:
        approved, reasoning, concerns = _parse_response(raw_text)
    except (json.JSONDecodeError, KeyError) as exc:
        log.error("Critic returned unparseable response: %s", exc)
        raise ValueError(f"Critic output could not be parsed: {exc}") from exc

    return CriticVerdict(
        id=str(uuid.uuid4()),
        patch_id=patch.id,
        approved=approved,
        reasoning=reasoning,
        concerns=concerns,
        model_used=settings.critic_model,
    )
