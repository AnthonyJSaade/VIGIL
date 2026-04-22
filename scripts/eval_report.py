"""Report rendering for the Vigil eval harness (Markdown + JSON summary).

Kept intentionally dumb: given :class:`RepoResult` objects and the aggregate
dict produced by :mod:`scripts.eval`, return a ready-to-write Markdown string
and a JSON-serialisable summary dict. No file I/O.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from scripts.eval import RepoResult


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _fmt_num(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{decimals}f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a GitHub-flavoured Markdown table."""
    if not rows:
        return f"| {' | '.join(headers)} |\n| {' | '.join(['---'] * len(headers))} |\n| _no data_ |\n"
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out) + "\n"


def render_summary_json(
    results: list["RepoResult"], aggregate: dict
) -> dict:
    """Build the `summary.json` payload."""
    return {
        "schema_version": 1,
        "aggregate": aggregate,
        "repos": [
            {
                "repo_id": r.repo_id,
                "language": r.language,
                "loc": r.loc,
                "truth_count": len(r.truth),
                "hunter_metrics": r.hunter_metrics,
                "surgeon_metrics": r.surgeon_metrics,
                "critic_metrics": r.critic_metrics,
                "end_to_end": r.end_to_end,
                "timings": r.timings,
            }
            for r in results
        ],
    }


def render_markdown(
    results: list["RepoResult"],
    aggregate: dict,
    *,
    generated_at: datetime,
) -> str:
    """Build `EVAL.md`."""
    ag_h = aggregate.get("hunter", {})
    ag_combined = ag_h.get("combined", {})
    ag_ete = aggregate.get("end_to_end", {})
    ag_semgrep = ag_h.get("semgrep", {})
    ag_llm = ag_h.get("llm", {})

    md: list[str] = []
    md.append("# Vigil Evaluation Report")
    md.append("")
    md.append(f"_Generated {generated_at.isoformat(timespec='seconds')}Z_")
    md.append("")

    md.append(
        "Across {repos} curated vibe-coded repos ({loc} LOC, {truth} planted vulnerabilities), "
        "Vigil's hybrid Hunter detected {det}/{truth} ({rec} recall, {prec} precision) "
        "and the Surgeon-Critic-Verifier pipeline produced a verified-clean fix for "
        "{fixed} of them ({fix_rate} end-to-end fix rate). "
        "{llm_only} findings were caught only by the LLM reviewer, not by Semgrep.".format(
            repos=len(results),
            loc=aggregate.get("loc_total", 0),
            truth=aggregate.get("truth_total", 0),
            det=ag_ete.get("detected", 0),
            rec=_fmt_pct(ag_combined.get("recall")),
            prec=_fmt_pct(ag_combined.get("precision")),
            fixed=ag_ete.get("verified_clean", 0),
            fix_rate=_fmt_pct(ag_ete.get("fix_rate")),
            llm_only=ag_h.get("llm_only_contribution_count", 0),
        )
    )
    md.append("")

    # --- Table 1: Headline summary -----------------------------------------
    md.append("## Headline summary")
    md.append("")
    rows = []
    for r in results:
        h = r.hunter_metrics.get("combined", {})
        ete = r.end_to_end
        rows.append([
            f"`{r.repo_id}`",
            str(r.loc),
            str(len(r.truth)),
            f"{ete.get('detected', 0)}/{len(r.truth)}",
            _fmt_pct(h.get("precision")),
            _fmt_pct(h.get("recall")),
            _fmt_num(h.get("f1")),
            f"{ete.get('verified_clean', 0)}/{len(r.truth)}",
        ])
    rows.append([
        "**Aggregate**",
        f"**{aggregate.get('loc_total', 0)}**",
        f"**{aggregate.get('truth_total', 0)}**",
        f"**{ag_ete.get('detected', 0)}/{aggregate.get('truth_total', 0)}**",
        f"**{_fmt_pct(ag_combined.get('precision'))}**",
        f"**{_fmt_pct(ag_combined.get('recall'))}**",
        f"**{_fmt_num(ag_combined.get('f1'))}**",
        f"**{ag_ete.get('verified_clean', 0)}/{aggregate.get('truth_total', 0)}**",
    ])
    md.append(_table(
        ["Repo", "LOC", "Truth", "Detected", "Precision", "Recall", "F1", "Fix rate"],
        rows,
    ))
    md.append("")

    # --- Table 2: Hunter breakdown ------------------------------------------
    md.append("## Hunter: Semgrep vs. LLM reviewer vs. hybrid")
    md.append("")
    md.append(
        "Recall denominators account for `detectable_by` tags in each truth manifest: "
        "Semgrep is scored only against findings its rulesets are expected to catch; "
        "the LLM reviewer is scored against all planted findings."
    )
    md.append("")
    hunter_rows = []
    for label, block in [
        ("Semgrep alone", ag_semgrep),
        ("LLM reviewer alone", ag_llm),
        ("Hybrid (union)", ag_combined),
    ]:
        hunter_rows.append([
            label,
            str(block.get("tp", 0)),
            str(block.get("fp", 0)),
            str(block.get("fn", 0)),
            str(block.get("expected", 0)),
            _fmt_pct(block.get("precision")),
            _fmt_pct(block.get("recall")),
            _fmt_num(block.get("f1")),
        ])
    md.append(_table(
        ["Scanner", "TP", "FP", "FN", "Expected", "Precision", "Recall", "F1"],
        hunter_rows,
    ))
    md.append("")
    md.append(
        f"**LLM-only contribution:** {ag_h.get('llm_only_contribution_count', 0)} "
        f"planted findings were detected by the LLM reviewer but missed by Semgrep."
    )
    md.append("")

    # --- Table 3: Surgeon ---------------------------------------------------
    md.append("## Surgeon")
    md.append("")
    ag_surgeon = aggregate.get("surgeon", {})
    surgeon_rows = [
        ["Patches attempted", str(ag_surgeon.get("patches_attempted", 0))],
        ["Applied cleanly to sandbox", str(ag_surgeon.get("patches_applied", 0))],
        ["Apply rate", _fmt_pct(ag_surgeon.get("apply_rate"))],
    ]
    md.append(_table(["Metric", "Value"], surgeon_rows))
    md.append("")

    # Per-repo Surgeon detail
    per_repo_surgeon = []
    for r in results:
        s = r.surgeon_metrics
        per_repo_surgeon.append([
            f"`{r.repo_id}`",
            str(s.get("patches_attempted", 0)),
            _fmt_pct(s.get("apply_rate")),
            _fmt_num(s.get("mean_attempts")),
            _fmt_pct(s.get("retry_rate")),
        ])
    md.append(_table(
        ["Repo", "Patches", "Apply rate", "Mean attempts", "Retry rate"],
        per_repo_surgeon,
    ))
    md.append("")

    # --- Table 4: Critic ----------------------------------------------------
    md.append("## Critic")
    md.append("")
    ag_critic = aggregate.get("critic", {})
    critic_rows = [
        ["Total verdicts", str(ag_critic.get("verdicts", 0))],
        [
            "Approved",
            f"{ag_critic.get('approved', 0)} ({_fmt_pct(ag_critic.get('approval_rate'))})",
        ],
        ["Rejected", str(ag_critic.get("rejected", 0))],
        [
            "Agreement with verifier (approved AND clean)",
            _fmt_pct(ag_critic.get("agreement_with_verifier")),
        ],
        [
            "False-accept rate (approved BUT dirty)",
            _fmt_pct(ag_critic.get("false_accept_rate")),
        ],
    ]
    md.append(_table(["Metric", "Value"], critic_rows))
    md.append("")

    # --- Table 5: End-to-end fix funnel ------------------------------------
    md.append("## End-to-end fix funnel")
    md.append("")
    total_truth = aggregate.get("truth_total", 0) or 1
    funnel = [
        ["Truth findings", str(aggregate.get("truth_total", 0)), "100.0%"],
        [
            "Detected by Hunter",
            str(ag_ete.get("detected", 0)),
            _fmt_pct(ag_ete.get("detection_rate")),
        ],
        [
            "Surgeon produced a patch",
            str(ag_ete.get("patched", 0)),
            _fmt_pct(ag_ete.get("patched", 0) / total_truth),
        ],
        [
            "Critic approved",
            str(ag_ete.get("approved", 0)),
            _fmt_pct(ag_ete.get("approved", 0) / total_truth),
        ],
        [
            "Verifier confirmed clean",
            str(ag_ete.get("verified_clean", 0)),
            _fmt_pct(ag_ete.get("fix_rate")),
        ],
    ]
    md.append(_table(["Stage", "Count", "% of truth"], funnel))
    md.append("")

    # --- Table 6: Timing ---------------------------------------------------
    md.append("## Timing")
    md.append("")
    timing_rows = []
    for r in results:
        t = r.timings
        timing_rows.append([
            f"`{r.repo_id}`",
            _fmt_num(t.get("scan_wallclock_s")),
            _fmt_num(t.get("patch_loop_p50_s")),
            _fmt_num(t.get("patch_loop_p95_s")),
            _fmt_num(t.get("verify_p50_s")),
            _fmt_num(t.get("verify_p95_s")),
        ])
    md.append(_table(
        ["Repo", "Scan (s)", "Patch p50 (s)", "Patch p95 (s)", "Verify p50 (s)", "Verify p95 (s)"],
        timing_rows,
    ))
    md.append("")

    # --- Per-repo deep dive -------------------------------------------------
    md.append("## Per-repo detail")
    md.append("")
    for r in results:
        md.append(f"### `{r.repo_id}`")
        md.append("")
        per = []
        for pipe_row in r.pipeline:
            detected = "yes" if pipe_row.detected else "no"
            scanner = pipe_row.detected_by or "-"
            patched = "yes" if pipe_row.patch_id else "no"
            if pipe_row.critic_approved is None:
                approved = "-"
            else:
                approved = "yes" if pipe_row.critic_approved else "no"
            if pipe_row.verification_clean is None:
                verified = "-"
            else:
                verified = "yes" if pipe_row.verification_clean else "no"
            per.append([
                pipe_row.truth_id,
                detected,
                scanner,
                patched,
                approved,
                verified,
            ])
        md.append(_table(
            ["Truth id", "Detected", "By scanner", "Patched", "Critic approved", "Verified clean"],
            per,
        ))

        llm_only = r.hunter_metrics.get("llm_only_contribution_truth_ids", [])
        if llm_only:
            md.append("")
            md.append(
                f"LLM-only contributions in this repo: "
                + ", ".join(f"`{x}`" for x in llm_only)
            )
        md.append("")

    return "\n".join(md).rstrip() + "\n"
