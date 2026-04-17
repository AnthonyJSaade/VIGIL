"""LLM-powered code reviewer — catches vulnerabilities that pattern-matching scanners miss.

Runs as the second phase of the Hunter pipeline, after Semgrep.  Receives
the Semgrep findings so it can skip duplicates and focus on logic flaws,
auth gaps, insecure defaults, and other issues that require reasoning.
"""

import json
import logging
import uuid
from pathlib import Path

import anthropic

from ..config import settings
from ..models.finding import Finding, SeverityLevel
from .source import read_source_lines

log = logging.getLogger(__name__)

_SCANNABLE_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".py", ".rb", ".go",
    ".java", ".php", ".html", ".yml", ".yaml", ".json",
    ".env", ".sh", ".sql",
}

_SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".next", "dist", "build"}

_SYSTEM_PROMPT = """\
You are a senior application security engineer performing a deep code review.
Your goal is to find vulnerabilities that automated pattern-matching scanners
(like Semgrep) typically MISS.

Focus on:
- Authentication and authorization logic flaws
- Missing security controls (rate limiting, CSRF, security headers)
- Insecure session management or token handling
- Business logic vulnerabilities
- Information leakage (verbose errors, debug endpoints)
- Insecure defaults and misconfigurations
- Race conditions and timing attacks
- Missing input validation beyond simple injection
- Insecure cryptographic usage
- Server-side request forgery (SSRF) patterns

Do NOT report vulnerabilities that are already listed in the "ALREADY DETECTED"
section below — those have been caught by the static scanner.

Return ONLY a JSON array.  Each element must have exactly these fields:
{
  "rule_id": "<descriptive-slug like missing-rate-limit or auth-bypass-no-session>",
  "severity": "<error | warning | info>",
  "file_path": "<relative path to the file>",
  "start_line": <integer>,
  "end_line": <integer>,
  "message": "<clear explanation of the vulnerability and its impact>",
  "confidence": <float 0.0 to 1.0>
}

Rules:
- Be conservative with confidence: use 0.8+ only when highly certain.
- severity "error" = exploitable vulnerability, "warning" = likely issue, "info" = hardening suggestion.
- If you find nothing new, return an empty array: []
- Do NOT wrap the JSON in markdown code fences.  Return raw JSON only.
"""


def _collect_files(repo_path: Path) -> dict[str, str]:
    """Read all scannable source files from the repo. Returns {relative_path: content}."""
    files: dict[str, str] = {}
    for path in sorted(repo_path.rglob("*")):
        if any(skip in path.parts for skip in _SKIP_DIRS):
            continue
        if path.is_file() and path.suffix in _SCANNABLE_EXTENSIONS:
            try:
                content = path.read_text(errors="replace")
                rel = str(path.relative_to(repo_path))
                files[rel] = content
            except OSError:
                continue
    return files


def _format_existing_findings(findings: list[Finding]) -> str:
    if not findings:
        return "None — the static scanner found no issues."
    lines = []
    for f in findings:
        lines.append(
            f"- [{f.severity}] {f.rule_id} in {f.file_path}:{f.start_line} — {f.message}"
        )
    return "\n".join(lines)


def _build_user_prompt(files: dict[str, str], existing: list[Finding]) -> str:
    parts = ["## ALREADY DETECTED (do NOT repeat these)\n"]
    parts.append(_format_existing_findings(existing))
    parts.append("\n\n## SOURCE CODE TO REVIEW\n")
    for rel_path, content in files.items():
        parts.append(f"### {rel_path}\n```\n{content}\n```\n")
    return "\n".join(parts)


_SEVERITY_MAP = {"error": SeverityLevel.ERROR, "warning": SeverityLevel.WARNING, "info": SeverityLevel.INFO}


def _parse_response(raw_text: str, run_id: str) -> list[Finding]:
    """Parse Claude's JSON response into Finding objects."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        log.warning("LLM reviewer returned unparseable JSON: %s...", text[:200])
        return []

    if not isinstance(items, list):
        log.warning("LLM reviewer returned non-array JSON")
        return []

    findings: list[Finding] = []
    for item in items:
        try:
            severity = _SEVERITY_MAP.get(item.get("severity", "info"), SeverityLevel.INFO)
            confidence = float(item.get("confidence", 0.7))
            confidence = max(0.0, min(1.0, confidence))

            findings.append(Finding(
                id=str(uuid.uuid4()),
                run_id=run_id,
                scanner="claude-review",
                rule_id=item.get("rule_id", "llm-finding"),
                severity=severity,
                message=item.get("message", ""),
                file_path=item.get("file_path", ""),
                start_line=int(item.get("start_line", 0)),
                end_line=int(item.get("end_line", 0)),
                snippet="",
                confidence=confidence,
                metadata={"source": "llm-review"},
            ))
        except (ValueError, TypeError, KeyError) as exc:
            log.warning("Skipping malformed LLM finding: %s", exc)
            continue

    return findings


async def review_code(
    repo_path: Path,
    run_id: str,
    existing_findings: list[Finding],
) -> list[Finding]:
    """Send repo source files to Claude for a deep security review.

    Returns additional :class:`Finding` objects with ``scanner="claude-review"``.
    On any failure (missing API key, parse error, etc.) returns an empty list —
    LLM findings are additive and must never block the pipeline.
    """
    if not settings.anthropic_api_key:
        log.warning("VIGIL_ANTHROPIC_API_KEY not set — skipping LLM review")
        return []

    files = _collect_files(repo_path)
    if not files:
        log.info("No scannable files found in %s", repo_path)
        return []

    user_prompt = _build_user_prompt(files, existing_findings)

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text
    except Exception as exc:
        log.error("LLM review API call failed: %s", exc)
        return []

    findings = _parse_response(raw_text, run_id)

    for f in findings:
        real = read_source_lines(repo_path, f.file_path, f.start_line, f.end_line)
        if real:
            f.snippet = real

    log.info("LLM review found %d additional findings", len(findings))
    return findings
