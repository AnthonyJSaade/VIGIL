"""Export bundle — collects run data and renders HTML report or ZIP archive."""

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..db import (
    get_findings_by_run,
    get_patches_by_finding,
    get_run,
    get_trace_events_by_run,
    get_verdict_by_patch,
    get_verification_by_patch,
)
from ..models import CriticVerdict, Finding, PatchProposal, Run, TraceEvent, VerificationReport

_TEMPLATE_DIR = Path(__file__).parent
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)


@dataclass
class PatchAttempt:
    """A single patch + its verdict and verification, pre-processed for the template."""
    patch: PatchProposal
    verdict: CriticVerdict | None
    verification: VerificationReport | None
    diff_lines: list[dict]


@dataclass
class FindingData:
    """A finding with all its associated patch attempts."""
    finding: Finding
    patches: list[PatchAttempt]


@dataclass
class RunData:
    """All data needed to render a run report."""
    run: Run
    findings: list[Finding]
    findings_data: list[FindingData]
    trace_events: list[TraceEvent]
    stats: dict


def _classify_diff_line(line: str) -> str:
    """Return a CSS class for a diff line."""
    if line.startswith("@@"):
        return "diff-hunk"
    if line.startswith("+"):
        return "diff-add"
    if line.startswith("-"):
        return "diff-del"
    return "diff-ctx"


def _parse_diff(diff_text: str) -> list[dict]:
    """Split a unified diff into lines with CSS classes for rendering."""
    return [
        {"text": line, "cls": _classify_diff_line(line)}
        for line in diff_text.splitlines()
    ]


async def _collect_run_data(run_id: str) -> RunData:
    """Gather all data for a run from the database."""
    run = await get_run(run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")

    findings = await get_findings_by_run(run_id)
    trace_events = await get_trace_events_by_run(run_id)

    findings_data: list[FindingData] = []
    total_patches = 0
    approved_count = 0

    for finding in findings:
        patches = await get_patches_by_finding(finding.id)
        patch_attempts: list[PatchAttempt] = []

        for patch in patches:
            total_patches += 1
            verdict = await get_verdict_by_patch(patch.id)
            verification = await get_verification_by_patch(patch.id)

            if verdict and verdict.approved:
                approved_count += 1

            patch_attempts.append(PatchAttempt(
                patch=patch,
                verdict=verdict,
                verification=verification,
                diff_lines=_parse_diff(patch.diff),
            ))

        findings_data.append(FindingData(finding=finding, patches=patch_attempts))

    error_count = sum(1 for f in findings if f.severity == "error")
    warning_count = sum(1 for f in findings if f.severity == "warning")
    info_count = sum(1 for f in findings if f.severity == "info")

    stats = {
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "total_patches": total_patches,
        "approved_count": approved_count,
    }

    return RunData(
        run=run,
        findings=findings,
        findings_data=findings_data,
        trace_events=trace_events,
        stats=stats,
    )


async def generate_html_report(run_id: str) -> str:
    """Render a self-contained HTML report for the given run."""
    data = await _collect_run_data(run_id)
    template = _jinja_env.get_template("report_template.html")
    return template.render(
        run=data.run,
        findings=data.findings,
        findings_data=data.findings_data,
        trace_events=data.trace_events,
        stats=data.stats,
    )


async def generate_zip_bundle(run_id: str) -> bytes:
    """Generate a ZIP archive containing the HTML report, findings JSON, trace JSON, and diffs."""
    data = await _collect_run_data(run_id)

    template = _jinja_env.get_template("report_template.html")
    html = template.render(
        run=data.run,
        findings=data.findings,
        findings_data=data.findings_data,
        trace_events=data.trace_events,
        stats=data.stats,
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.html", html)

        findings_json = [f.model_dump(mode="json") for f in data.findings]
        zf.writestr("findings.json", json.dumps(findings_json, indent=2))

        trace_json = [e.model_dump(mode="json") for e in data.trace_events]
        zf.writestr("trace.json", json.dumps(trace_json, indent=2))

        for fd in data.findings_data:
            for pa in fd.patches:
                prefix = f"patches/{fd.finding.id}"
                zf.writestr(f"{prefix}/patch_{pa.patch.attempt}.diff", pa.patch.diff)
                if pa.verdict:
                    verdict_json = pa.verdict.model_dump(mode="json")
                    zf.writestr(
                        f"{prefix}/verdict_{pa.patch.attempt}.json",
                        json.dumps(verdict_json, indent=2),
                    )

    return buf.getvalue()
