"""Surgeon agent — generates minimal security patches via Claude.

The Surgeon returns the **full patched file content** (not a diff). The
backend computes a unified diff deterministically with ``difflib`` so the
diff is guaranteed to be well-formed and to match the real source file
context exactly — LLM-generated diffs are notorious for hallucinated
context lines and broken hunk counts, which wrecked sandbox application.

Supports retry: when called with ``prior_concerns``, the Surgeon adjusts
the patched file to address the Critic's objections.
"""

import difflib
import json
import logging
import uuid

import anthropic

from ..config import settings
from ..models.finding import Finding
from ..models.patch import PatchProposal

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the Surgeon — a senior security engineer who writes minimal, \
targeted patches.

Rules:
1. Fix ONLY the specific vulnerability described. Do not refactor, improve \
style, or add features.
2. Keep the change as small as possible — every changed line must be justified.
3. Preserve existing functionality. The change must not break tests or \
introduce regressions.
4. Use secure coding patterns: parameterized queries, allow-lists, proper \
escaping, env-based secrets, etc.
5. Never suppress a scanner rule, remove authentication, or widen trust \
boundaries as a "fix".

Return ONLY a JSON object with exactly these fields:
{
  "patched_content": "<the FULL updated source file content, byte-for-byte, with your minimal edit applied>",
  "explanation": "<2-3 sentence explanation of what the patch does and why>"
}

Requirements for ``patched_content``:
- It must be the COMPLETE file, not a snippet or a diff.
- Preserve every line you did not need to change exactly as-is, including \
whitespace, indentation, trailing newline, and comments.
- Do NOT include markdown code fences, escape sequences, or any wrapper — \
just the raw source as a JSON string.

Do NOT wrap the JSON response in markdown code fences. Return raw JSON only.
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
    """Extract patched_content and explanation from Claude's JSON response."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    data = json.loads(text)
    return data["patched_content"], data["explanation"]


def _compute_diff(original: str, patched: str, file_path: str) -> str:
    """Produce a well-formed unified diff from before/after file contents.

    Uses the standard ``a/<path> b/<path>`` header convention so the sandbox
    verifier's ``-p1`` path resolution works by default. ``splitlines
    (keepends=True)`` preserves each line's original newline, which keeps
    ``difflib``'s output byte-accurate for binary-clean text files.
    """
    old_lines = original.splitlines(keepends=True)
    new_lines = patched.splitlines(keepends=True)
    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=3,
    )
    return "".join(diff_lines)


async def propose_patch(
    finding: Finding,
    file_content: str,
    prior_concerns: list[str] | None = None,
    attempt: int = 1,
) -> PatchProposal:
    """Call Claude to generate a minimal patch for the given finding.

    The Surgeon returns the full patched file; we compute the unified diff
    locally so it is always well-formed and matches real context exactly.

    Args:
        finding: The vulnerability to fix.
        file_content: Full content of the affected source file.
        prior_concerns: Critic's objections from a previous attempt (retry).
        attempt: Attempt number (1 = first try, 2 = retry after rejection).

    Returns:
        A :class:`PatchProposal` with the computed unified diff and explanation.

    Raises:
        ValueError: If the API key is missing or Claude returns unparseable output.
    """
    if not settings.anthropic_api_key:
        raise ValueError("VIGIL_ANTHROPIC_API_KEY is not configured")

    user_prompt = _build_user_prompt(finding, file_content, prior_concerns)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.surgeon_model,
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw_text = response.content[0].text

    try:
        patched_content, explanation = _parse_response(raw_text)
    except (json.JSONDecodeError, KeyError) as exc:
        log.error("Surgeon returned unparseable response: %s", exc)
        raise ValueError(f"Surgeon output could not be parsed: {exc}") from exc

    if patched_content == file_content:
        log.warning(
            "Surgeon returned unchanged content for finding %s (attempt %d)",
            finding.id,
            attempt,
        )

    diff = _compute_diff(file_content, patched_content, finding.file_path)

    return PatchProposal(
        id=str(uuid.uuid4()),
        finding_id=finding.id,
        diff=diff,
        explanation=explanation,
        model_used=settings.surgeon_model,
        attempt=attempt,
        prior_concerns=prior_concerns,
    )
