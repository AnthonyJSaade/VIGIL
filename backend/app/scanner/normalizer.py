"""Deterministic normalizer — converts raw Semgrep JSON into typed Finding objects."""

import uuid
from pathlib import Path

from ..models.finding import Finding, SeverityLevel
from .source import read_source_lines

# Semgrep outputs severity in UPPERCASE; map to our enum.
_SEVERITY_MAP: dict[str, SeverityLevel] = {
    "ERROR": SeverityLevel.ERROR,
    "CRITICAL": SeverityLevel.ERROR,
    "HIGH": SeverityLevel.ERROR,
    "WARNING": SeverityLevel.WARNING,
    "MEDIUM": SeverityLevel.WARNING,
    "INFO": SeverityLevel.INFO,
    "LOW": SeverityLevel.INFO,
    "INVENTORY": SeverityLevel.INFO,
    "EXPERIMENT": SeverityLevel.INFO,
}


def _map_severity(raw: str) -> SeverityLevel:
    return _SEVERITY_MAP.get(raw.upper(), SeverityLevel.INFO)


def normalize_findings(
    raw: dict,
    run_id: str,
    repo_path: Path | None = None,
) -> list[Finding]:
    """Convert Semgrep JSON output into a list of :class:`Finding` objects.

    This function is fully deterministic — no LLM calls, no network access.
    Each Semgrep ``cli_match`` in ``raw["results"]`` becomes one Finding.

    When ``repo_path`` is provided, the snippet is pulled from the real source
    file at the matched line range. Semgrep's ``extra.lines`` is kept only as a
    last-resort fallback because some rules fill it with metadata text rather
    than the source code.
    """
    findings: list[Finding] = []

    for match in raw.get("results", []):
        extra = match.get("extra", {})
        raw_path = match.get("path", "")
        start_line = match.get("start", {}).get("line", 0)
        end_line = match.get("end", {}).get("line", 0)

        real_snippet = ""
        if repo_path is not None:
            real_snippet = read_source_lines(repo_path, raw_path, start_line, end_line)

        # Semgrep emits absolute paths when invoked with an absolute repo root
        # (e.g. ``/demo-repos/vibe-todo-app/server.js``). Always normalize to a
        # repo-relative path so downstream consumers — the Surgeon's diff
        # headers, the sandbox `patch` strip logic, the UI, and the HTML/ZIP
        # exporters — can trust ``finding.file_path`` as-is. Falls back to a
        # best-effort lstrip if the match isn't under the repo root (which
        # shouldn't happen in practice, but keeps normalization safe).
        file_path = raw_path
        if repo_path is not None and raw_path:
            try:
                file_path = str(Path(raw_path).resolve().relative_to(repo_path.resolve()))
            except ValueError:
                file_path = raw_path.lstrip("/")
        else:
            file_path = raw_path.lstrip("/")

        snippet = real_snippet or extra.get("lines", "")

        finding = Finding(
            id=str(uuid.uuid4()),
            run_id=run_id,
            scanner="semgrep",
            rule_id=match.get("check_id", "unknown"),
            severity=_map_severity(extra.get("severity", "INFO")),
            message=extra.get("message", ""),
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            snippet=snippet,
            metadata=extra.get("metadata", {}),
        )
        findings.append(finding)

    return findings


if __name__ == "__main__":
    sample_semgrep_output = {
        "version": {"version": "1.50.0"},
        "results": [
            {
                "check_id": "javascript.lang.security.audit.detect-eval-with-expression",
                "path": "server.js",
                "start": {"line": 45, "col": 5, "offset": 1023},
                "end": {"line": 45, "col": 30, "offset": 1048},
                "extra": {
                    "message": "Detected eval() usage with a non-literal argument.",
                    "metadata": {
                        "cwe": ["CWE-95"],
                        "owasp": ["A03:2021"],
                    },
                    "severity": "ERROR",
                    "fingerprint": "abc123",
                    "lines": "    eval(req.body.filter)",
                },
            },
            {
                "check_id": "javascript.express.security.audit.detect-sql-injection",
                "path": "server.js",
                "start": {"line": 22, "col": 5, "offset": 500},
                "end": {"line": 22, "col": 60, "offset": 555},
                "extra": {
                    "message": "Detected string concatenation in SQL query.",
                    "metadata": {"cwe": ["CWE-89"]},
                    "severity": "WARNING",
                    "fingerprint": "def456",
                    "lines": '    db.query("SELECT * FROM todos WHERE user = \'" + userId + "\'")',
                },
            },
            {
                "check_id": "generic.secrets.security.detected-jwt-secret",
                "path": "server.js",
                "start": {"line": 5, "col": 1, "offset": 80},
                "end": {"line": 5, "col": 50, "offset": 130},
                "extra": {
                    "message": "Hardcoded JWT secret detected.",
                    "metadata": {},
                    "severity": "CRITICAL",
                    "fingerprint": "ghi789",
                    "lines": 'const JWT_SECRET = "super-secret-key-123"',
                },
            },
        ],
        "errors": [],
        "paths": {"scanned": ["server.js"]},
    }

    findings = normalize_findings(sample_semgrep_output, run_id="test-run-001")

    assert len(findings) == 3

    f0 = findings[0]
    assert f0.rule_id == "javascript.lang.security.audit.detect-eval-with-expression"
    assert f0.severity == SeverityLevel.ERROR
    assert f0.start_line == 45
    assert "eval" in f0.snippet

    f1 = findings[1]
    assert f1.severity == SeverityLevel.WARNING

    f2 = findings[2]
    assert f2.severity == SeverityLevel.ERROR  # CRITICAL maps to ERROR

    for f in findings:
        assert f.run_id == "test-run-001"
        assert f.scanner == "semgrep"

    print(f"Normalizer test passed: {len(findings)} findings")
    for f in findings:
        print(f"  [{f.severity}] {f.rule_id} @ {f.file_path}:{f.start_line}")
