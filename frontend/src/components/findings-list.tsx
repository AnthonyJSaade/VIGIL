// FindingsList — filterable list of findings for a completed run.
//
// Calls GET /api/runs/{run_id}/findings, passing the chosen severity as a
// query param so the backend applies the filter. Re-fetches whenever the
// dropdown changes. Claude-sourced findings are tagged "AI Review" in purple
// to distinguish them from deterministic Semgrep findings.
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import SeverityBadge from "./severity-badge";

const API_BASE = "http://localhost:8000";

interface FindingSummary {
  id: string;
  run_id: string;
  scanner: string;
  rule_id: string;
  severity: string;
  message: string;
  file_path: string;
  start_line: number;
  end_line: number;
  confidence: number;
  created_at: string;
}

export default function FindingsList({ runId }: { runId: string }) {
  const [findings, setFindings] = useState<FindingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState<string>("all");

  useEffect(() => {
    async function load() {
      try {
        const url = new URL(`${API_BASE}/api/runs/${runId}/findings`);
        if (severityFilter !== "all") {
          url.searchParams.set("severity", severityFilter);
        }
        const res = await fetch(url.toString(), { cache: "no-store" });
        if (res.ok) {
          setFindings(await res.json());
        }
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [runId, severityFilter]);

  if (loading) {
    return <p className="text-sm text-zinc-500">Loading findings...</p>;
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-100">
          Findings ({findings.length})
        </h3>
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-300"
        >
          <option value="all">All severities</option>
          <option value="error">Error</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
      </div>

      {findings.length === 0 ? (
        <p className="text-sm text-zinc-500">No findings match the filter.</p>
      ) : (
        <div className="space-y-2">
          {findings.map((f) => (
            <Link
              key={f.id}
              href={`/findings/${f.id}`}
              className="flex items-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 transition-colors hover:border-zinc-700 hover:bg-zinc-800"
            >
              <SeverityBadge severity={f.severity} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-zinc-200">
                  {f.message}
                </p>
                <p className="mt-0.5 truncate font-mono text-xs text-zinc-500">
                  {f.file_path}:{f.start_line}
                  {f.scanner === "claude-review" && (
                    <span className="ml-2 text-purple-400">AI Review</span>
                  )}
                </p>
              </div>
              <span className="shrink-0 font-mono text-xs text-zinc-600">
                {f.rule_id}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
