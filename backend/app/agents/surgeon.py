"""Surgeon agent — generates minimal security patches via Claude.

Given a finding and the full source file, the Surgeon produces a unified diff
that fixes the vulnerability with the smallest possible change.  Supports
retry: when called with ``prior_concerns``, it adjusts the patch to address
the Critic's objections.
"""

import json
import logging
import uuid

import anthropic

from ..config import settings
from ..models.finding import Finding
from ..models.patch import PatchProposal

log = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"

_SYSTEM_PROMPT = """\
You are the Surgeon — a senior security engineer who writes minimal, \
targeted patches.

Rules:
1. Fix ONLY the specific vulnerability described. Do not refactor, improve \
style, or add features.
2. Output a unified diff (--- a/path, +++ b/path, @@ hunk headers, - and + \
lines). Nothing else outside the JSON.
3. Keep the patch as small as possible — every changed line must be justified.
4. Preserve existing functionality. The patch must not break tests or \
introduce regressions.
5. Use secure coding patterns: parameterized queries, allow-lists, proper \
escaping, env-based secrets, etc.
6. Never suppress a scanner rule, remove authentication, or widen trust \
boundaries as a "fix".

Return ONLY a JSON object with exactly these fields:
{
  "diff": "<unified diff string>",
  "explanation": "<2-3 sentence explanation of what the patch does and why>"
}

Do NOT wrap the JSON in markdown code fences. Return raw JSON only.
"""


def _build_user_prompt(
    finding: Finding,
    file_content: str,
    prior_concerns: list[str] | None = None,
) -> str:
    parts = [
        "## Vulnerability to Fix\n",
        f"**Rule**: {finding.rule_id}\n",
        f"**Severity**: {finding.severity.value}\n",
        f"**File**: {finding.file_path}\n",
        f"**Lines**: {finding.start_line}–{finding.end_line}\n",
        f"**Message**: {finding.message}\n",
    ]

    if finding.snippet:
        parts.append(f"\n**Vulnerable snippet**:\n```\n{finding.snippet}\n```\n")

    parts.append(f"\n## Full Source File ({finding.file_path})\n```\n{file_content}\n```\n")

    if prior_concerns:
        parts.append("\n## Critic's Concerns (address these in your revised patch)\n")
        for i, concern in enumerate(prior_concerns, 1):
            parts.append(f"{i}. {concern}\n")

    return "\n".join(parts)


def _parse_response(raw_text: str) -> tuple[str, str]:
    """Extract diff and explanation from Claude's JSON response."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    data = json.loads(text)
    return data["diff"], data["explanation"]


async def propose_patch(
    finding: Finding,
    file_content: str,
    prior_concerns: list[str] | None = None,
    attempt: int = 1,
) -> PatchProposal:
    """Call Claude to generate a minimal patch for the given finding.

    Args:
        finding: The vulnerability to fix.
        file_content: Full content of the affected source file.
        prior_concerns: Critic's objections from a previous attempt (retry).
        attempt: Attempt number (1 = first try, 2 = retry after rejection).

    Returns:
        A :class:`PatchProposal` with the unified diff and explanation.

    Raises:
        ValueError: If the API key is missing or Claude returns unparseable output.
    """
    if not settings.anthropic_api_key:
        raise ValueError("VIGIL_ANTHROPIC_API_KEY is not configured")

    user_prompt = _build_user_prompt(finding, file_content, prior_concerns)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw_text = response.content[0].text

    try:
        diff, explanation = _parse_response(raw_text)
    except (json.JSONDecodeError, KeyError) as exc:
        log.error("Surgeon returned unparseable response: %s", exc)
        raise ValueError(f"Surgeon output could not be parsed: {exc}") from exc

    return PatchProposal(
        id=str(uuid.uuid4()),
        finding_id=finding.id,
        diff=diff,
        explanation=explanation,
        model_used=_MODEL,
        attempt=attempt,
        prior_concerns=prior_concerns,
    )
