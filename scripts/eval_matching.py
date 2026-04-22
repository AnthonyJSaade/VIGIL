"""Finding-to-truth matcher for the Vigil eval harness.

Pure, side-effect-free assignment of reported findings to ground-truth entries
from `.vigil/truth.yaml`. Every unresolved ambiguity here shows up as noise in
the final precision/recall numbers, so the logic is deliberately conservative
and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field


LINE_TOLERANCE = 5


@dataclass(frozen=True)
class TruthFinding:
    """Ground-truth entry loaded from a repo's `.vigil/truth.yaml`."""

    id: str
    cwe: str
    kind: str
    file: str
    lines: tuple[int, ...]
    severity: str
    detectable_by: frozenset[str]
    notes: str = ""

    @classmethod
    def from_yaml_entry(cls, entry: dict) -> "TruthFinding":
        raw_lines = entry.get("lines")
        if raw_lines is None:
            single = entry.get("line")
            raw_lines = [single] if single is not None else []
        return cls(
            id=entry["id"],
            cwe=entry["cwe"],
            kind=entry["kind"],
            file=entry["file"],
            lines=tuple(int(x) for x in raw_lines),
            severity=entry.get("severity", "medium"),
            detectable_by=frozenset(entry.get("detectable_by", ["llm"])),
            notes=entry.get("notes", ""),
        )


@dataclass(frozen=True)
class ReportedFinding:
    """Minimal view of a Vigil-reported finding the matcher needs.

    The harness constructs these from :class:`Finding` rows in eval.db so this
    module has zero dependency on the backend codebase and can be unit-tested
    in isolation.
    """

    id: str
    scanner: str
    rule_id: str
    file_path: str
    start_line: int
    end_line: int
    metadata_cwe: str | None = None


@dataclass
class Match:
    truth_id: str
    finding_id: str
    reason: str
    line_distance: int


@dataclass
class MatchResult:
    """Outcome of matching one repo's findings against its truth manifest."""

    matches: list[Match] = field(default_factory=list)
    unmatched_truth: list[str] = field(default_factory=list)
    unmatched_findings: list[str] = field(default_factory=list)
    duplicate_findings: list[str] = field(default_factory=list)

    @property
    def truth_to_finding(self) -> dict[str, str]:
        return {m.truth_id: m.finding_id for m in self.matches}

    @property
    def finding_to_truth(self) -> dict[str, str]:
        return {m.finding_id: m.truth_id for m in self.matches}


def _same_file(report_path: str, truth_path: str) -> bool:
    """Tolerant file equivalence check.

    Handles: identical paths, one path being a suffix of the other (e.g. a
    scanner reporting `demo-repos/foo/server.js` when truth says `server.js`),
    and basename-only equivalence as a last resort.
    """
    if not report_path or not truth_path:
        return False

    def _norm(p: str) -> str:
        return p.replace("\\", "/").lstrip("./").lstrip("/")

    r = _norm(report_path)
    t = _norm(truth_path)

    if r == t:
        return True
    if r.endswith("/" + t) or t.endswith("/" + r):
        return True
    return r.rsplit("/", 1)[-1] == t.rsplit("/", 1)[-1]


def _min_line_distance(
    reported: ReportedFinding, truth: TruthFinding
) -> int | None:
    """Smallest gap between the reported line range and any truth line.

    Returns ``None`` when the truth entry has no line data (shouldn't happen
    with our schema but we stay defensive).
    """
    if not truth.lines:
        return None
    lo, hi = reported.start_line, reported.end_line
    if hi < lo:
        lo, hi = hi, lo
    best = None
    for t_line in truth.lines:
        if lo <= t_line <= hi:
            distance = 0
        else:
            distance = min(abs(t_line - lo), abs(t_line - hi))
        if best is None or distance < best:
            best = distance
    return best


def _cwe_matches(reported: ReportedFinding, truth: TruthFinding) -> bool:
    """True if the reported finding advertises the same CWE as the truth entry.

    CWE can show up in the rule_id (e.g. `cwe-89-sqli-...`) or in metadata.
    """
    needle = truth.cwe.lower()
    if reported.metadata_cwe and needle in reported.metadata_cwe.lower():
        return True
    return needle in (reported.rule_id or "").lower()


def _score_candidate(
    reported: ReportedFinding, truth: TruthFinding
) -> tuple[int, int, str] | None:
    """Return a (priority, distance, reason) tuple if this pair could match.

    Priority is lower-is-better so we can rank with :func:`min`:
      0 = exact line hit inside tolerance
      1 = line proximity within tolerance
      2 = same-file CWE match without usable line data
    """
    if not _same_file(reported.file_path, truth.file):
        return None

    distance = _min_line_distance(reported, truth)
    if distance is not None:
        if distance == 0:
            return (0, 0, "line-exact")
        if distance <= LINE_TOLERANCE:
            return (1, distance, f"line-proximity-{distance}")

    if _cwe_matches(reported, truth):
        return (2, 10_000, "cwe-in-file")

    return None


def match_findings(
    reported: list[ReportedFinding],
    truth: list[TruthFinding],
) -> MatchResult:
    """Greedy one-to-one assignment of reported findings to truth entries.

    Best global score wins first (lowest priority, then smallest line distance).
    A truth entry matches at most one reported finding; extra overlapping
    findings are simply dropped (neither TP nor FP) so multi-line bugs like the
    combined ``sqli-todos`` entry don't inflate FP counts.
    """
    result = MatchResult()

    scored: list[tuple[tuple[int, int, str], TruthFinding, ReportedFinding]] = []
    for t in truth:
        for r in reported:
            score = _score_candidate(r, t)
            if score is not None:
                scored.append((score, t, r))

    scored.sort(key=lambda row: row[0])

    used_truth: set[str] = set()
    used_findings: set[str] = set()
    duplicate_findings: set[str] = set()

    for score, t, r in scored:
        if t.id in used_truth:
            duplicate_findings.add(r.id)
            continue
        if r.id in used_findings:
            continue
        result.matches.append(
            Match(
                truth_id=t.id,
                finding_id=r.id,
                reason=score[2],
                line_distance=score[1],
            )
        )
        used_truth.add(t.id)
        used_findings.add(r.id)

    result.unmatched_truth = [t.id for t in truth if t.id not in used_truth]
    result.unmatched_findings = [
        r.id
        for r in reported
        if r.id not in used_findings and r.id not in duplicate_findings
    ]
    result.duplicate_findings = sorted(duplicate_findings)
    return result
