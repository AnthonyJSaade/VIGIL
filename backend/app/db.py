"""SQLite persistence layer — schema, connection management, and CRUD helpers."""

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

import aiosqlite

from .config import settings
from .models import (
    CriticVerdict,
    Finding,
    PatchProposal,
    Run,
    VerificationReport,
    TraceEvent,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    finding_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    scanner TEXT NOT NULL DEFAULT 'semgrep',
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    snippet TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patches (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL REFERENCES findings(id),
    diff TEXT NOT NULL,
    explanation TEXT NOT NULL,
    model_used TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    prior_concerns TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verdicts (
    id TEXT PRIMARY KEY,
    patch_id TEXT NOT NULL REFERENCES patches(id),
    approved INTEGER NOT NULL,
    reasoning TEXT NOT NULL,
    concerns TEXT NOT NULL DEFAULT '[]',
    model_used TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verifications (
    id TEXT PRIMARY KEY,
    patch_id TEXT NOT NULL REFERENCES patches(id),
    scanner_rerun_clean INTEGER NOT NULL,
    tests_passed INTEGER,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trace_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT NOT NULL
);
"""


async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with aiosqlite.connect(settings.db_path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager yielding a database connection."""
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

async def insert_run(run: Run) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO runs (id, repo_id, status, finding_count, created_at) VALUES (?, ?, ?, ?, ?)",
            (run.id, run.repo_id, run.status, run.finding_count, _iso(run.created_at)),
        )
        await db.commit()


async def get_run(run_id: str) -> Run | None:
    async with get_db() as db:
        row = await db.execute_fetchall(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        )
        if not row:
            return None
        r = row[0]
        return Run(
            id=r["id"], repo_id=r["repo_id"], status=r["status"],
            finding_count=r["finding_count"], created_at=_parse_dt(r["created_at"]),
        )


async def update_run_status(run_id: str, status: str, finding_count: int | None = None) -> None:
    async with get_db() as db:
        if finding_count is not None:
            await db.execute(
                "UPDATE runs SET status = ?, finding_count = ? WHERE id = ?",
                (status, finding_count, run_id),
            )
        else:
            await db.execute(
                "UPDATE runs SET status = ? WHERE id = ?",
                (status, run_id),
            )
        await db.commit()


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

async def insert_finding(finding: Finding) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO findings (id, run_id, scanner, rule_id, severity, message, file_path, start_line, end_line, snippet, confidence, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                finding.id, finding.run_id, finding.scanner, finding.rule_id,
                finding.severity, finding.message, finding.file_path,
                finding.start_line, finding.end_line, finding.snippet,
                finding.confidence, json.dumps(finding.metadata),
                _iso(finding.created_at),
            ),
        )
        await db.commit()


async def insert_findings_batch(findings: list[Finding]) -> None:
    """Insert multiple findings in a single transaction."""
    if not findings:
        return
    async with get_db() as db:
        await db.executemany(
            "INSERT INTO findings (id, run_id, scanner, rule_id, severity, message, file_path, start_line, end_line, snippet, confidence, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    f.id, f.run_id, f.scanner, f.rule_id, f.severity,
                    f.message, f.file_path, f.start_line, f.end_line,
                    f.snippet, f.confidence, json.dumps(f.metadata),
                    _iso(f.created_at),
                )
                for f in findings
            ],
        )
        await db.commit()


async def get_findings_by_run(run_id: str) -> list[Finding]:
    async with get_db() as db:
        rows = await db.execute_fetchall(
            """SELECT * FROM findings WHERE run_id = ?
               ORDER BY CASE severity
                   WHEN 'error'   THEN 0
                   WHEN 'warning' THEN 1
                   WHEN 'info'    THEN 2
                   ELSE 3
               END, file_path""",
            (run_id,),
        )
        return [
            Finding(
                id=r["id"], run_id=r["run_id"], scanner=r["scanner"],
                rule_id=r["rule_id"], severity=r["severity"], message=r["message"],
                file_path=r["file_path"], start_line=r["start_line"],
                end_line=r["end_line"], snippet=r["snippet"],
                confidence=r["confidence"],
                metadata=json.loads(r["metadata"]), created_at=_parse_dt(r["created_at"]),
            )
            for r in rows
        ]


async def get_finding(finding_id: str) -> Finding | None:
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM findings WHERE id = ?", (finding_id,)
        )
        if not rows:
            return None
        r = rows[0]
        return Finding(
            id=r["id"], run_id=r["run_id"], scanner=r["scanner"],
            rule_id=r["rule_id"], severity=r["severity"], message=r["message"],
            file_path=r["file_path"], start_line=r["start_line"],
            end_line=r["end_line"], snippet=r["snippet"],
            confidence=r["confidence"],
            metadata=json.loads(r["metadata"]), created_at=_parse_dt(r["created_at"]),
        )


# ---------------------------------------------------------------------------
# Patches
# ---------------------------------------------------------------------------

async def insert_patch(patch: PatchProposal) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO patches (id, finding_id, diff, explanation, model_used, attempt, prior_concerns, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                patch.id, patch.finding_id, patch.diff, patch.explanation,
                patch.model_used, patch.attempt,
                json.dumps(patch.prior_concerns) if patch.prior_concerns else None,
                _iso(patch.created_at),
            ),
        )
        await db.commit()


async def get_patch(patch_id: str) -> PatchProposal | None:
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM patches WHERE id = ?", (patch_id,)
        )
        if not rows:
            return None
        r = rows[0]
        return PatchProposal(
            id=r["id"], finding_id=r["finding_id"], diff=r["diff"],
            explanation=r["explanation"], model_used=r["model_used"],
            attempt=r["attempt"],
            prior_concerns=json.loads(r["prior_concerns"]) if r["prior_concerns"] else None,
            created_at=_parse_dt(r["created_at"]),
        )


async def get_patches_by_finding(finding_id: str) -> list[PatchProposal]:
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM patches WHERE finding_id = ? ORDER BY attempt",
            (finding_id,),
        )
        return [
            PatchProposal(
                id=r["id"], finding_id=r["finding_id"], diff=r["diff"],
                explanation=r["explanation"], model_used=r["model_used"],
                attempt=r["attempt"],
                prior_concerns=json.loads(r["prior_concerns"]) if r["prior_concerns"] else None,
                created_at=_parse_dt(r["created_at"]),
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

async def insert_verdict(verdict: CriticVerdict) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO verdicts (id, patch_id, approved, reasoning, concerns, model_used, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                verdict.id, verdict.patch_id, int(verdict.approved),
                verdict.reasoning, json.dumps(verdict.concerns),
                verdict.model_used, _iso(verdict.created_at),
            ),
        )
        await db.commit()


async def get_verdict_by_patch(patch_id: str) -> CriticVerdict | None:
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM verdicts WHERE patch_id = ?", (patch_id,)
        )
        if not rows:
            return None
        r = rows[0]
        return CriticVerdict(
            id=r["id"], patch_id=r["patch_id"], approved=bool(r["approved"]),
            reasoning=r["reasoning"], concerns=json.loads(r["concerns"]),
            model_used=r["model_used"], created_at=_parse_dt(r["created_at"]),
        )


# ---------------------------------------------------------------------------
# Verifications
# ---------------------------------------------------------------------------

async def insert_verification(report: VerificationReport) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO verifications (id, patch_id, scanner_rerun_clean, tests_passed, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                report.id, report.patch_id, int(report.scanner_rerun_clean),
                int(report.tests_passed) if report.tests_passed is not None else None,
                report.details, _iso(report.created_at),
            ),
        )
        await db.commit()


async def get_verification_by_patch(patch_id: str) -> VerificationReport | None:
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM verifications WHERE patch_id = ?", (patch_id,)
        )
        if not rows:
            return None
        r = rows[0]
        return VerificationReport(
            id=r["id"], patch_id=r["patch_id"],
            scanner_rerun_clean=bool(r["scanner_rerun_clean"]),
            tests_passed=bool(r["tests_passed"]) if r["tests_passed"] is not None else None,
            details=r["details"], created_at=_parse_dt(r["created_at"]),
        )


async def delete_verification_by_patch(patch_id: str) -> None:
    """Remove any stored verification report for *patch_id* (used for re-runs)."""
    async with get_db() as db:
        await db.execute("DELETE FROM verifications WHERE patch_id = ?", (patch_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# Trace Events
# ---------------------------------------------------------------------------

async def insert_trace_event(event: TraceEvent) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO trace_events (id, run_id, role, action, payload, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.id, event.run_id, event.role, event.action,
                json.dumps(event.payload), _iso(event.timestamp),
            ),
        )
        await db.commit()


async def get_trace_events_by_run(run_id: str) -> list[TraceEvent]:
    async with get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM trace_events WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        )
        return [
            TraceEvent(
                id=r["id"], run_id=r["run_id"], role=r["role"],
                action=r["action"], payload=json.loads(r["payload"]),
                timestamp=_parse_dt(r["timestamp"]),
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    import tempfile
    import os
    from .models import SeverityLevel, AgentRole, TraceAction

    async def _smoke_test() -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        settings.db_path = tmp.name

        try:
            await init_db()

            # --- Run CRUD ---
            test_run = Run(id="run-001", repo_id="demo-1")
            await insert_run(test_run)

            fetched = await get_run("run-001")
            assert fetched is not None
            assert fetched.id == "run-001"
            assert fetched.repo_id == "demo-1"
            assert fetched.status == "pending"

            await update_run_status("run-001", "completed", finding_count=3)
            fetched = await get_run("run-001")
            assert fetched is not None
            assert fetched.status == "completed"
            assert fetched.finding_count == 3
            print("  Run CRUD: OK")

            # --- Finding batch insert + severity ordering ---
            findings = [
                Finding(id="f-info", run_id="run-001", rule_id="r1",
                        severity=SeverityLevel.INFO, message="info msg",
                        file_path="a.js", start_line=1, end_line=1, snippet="x"),
                Finding(id="f-warn", run_id="run-001", rule_id="r2",
                        severity=SeverityLevel.WARNING, message="warn msg",
                        file_path="a.js", start_line=10, end_line=10, snippet="y"),
                Finding(id="f-err", run_id="run-001", rule_id="r3",
                        severity=SeverityLevel.ERROR, message="err msg",
                        file_path="a.js", start_line=20, end_line=20, snippet="z"),
            ]
            await insert_findings_batch(findings)

            fetched_findings = await get_findings_by_run("run-001")
            assert len(fetched_findings) == 3
            assert fetched_findings[0].severity == SeverityLevel.ERROR
            assert fetched_findings[1].severity == SeverityLevel.WARNING
            assert fetched_findings[2].severity == SeverityLevel.INFO

            single = await get_finding("f-warn")
            assert single is not None
            assert single.message == "warn msg"
            print("  Finding CRUD + ordering: OK")

            # --- TraceEvent CRUD ---
            evt = TraceEvent(id="t-001", run_id="run-001",
                             role=AgentRole.HUNTER, action=TraceAction.SCAN_STARTED,
                             payload={"repo": "demo-1"})
            await insert_trace_event(evt)

            events = await get_trace_events_by_run("run-001")
            assert len(events) == 1
            assert events[0].role == AgentRole.HUNTER
            assert events[0].payload == {"repo": "demo-1"}
            print("  TraceEvent CRUD: OK")

            print("DB smoke test passed (all tables)")
        finally:
            os.unlink(tmp.name)

    asyncio.run(_smoke_test())
