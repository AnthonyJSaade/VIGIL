// Run page — live view of an in-progress or completed audit run.
//
// Renders three sections in sequence:
//   1. Status header (pending → scanning → completed / failed)
//   2. LiveFeed — SSE event stream showing Hunter, Surgeon, and Critic activity
//   3. FindingsList — appears once the run reaches a terminal state
//
// The run summary is fetched once on mount, then re-fetched 500 ms after the
// SSE stream signals scan_completed. The delay gives the database time to
// commit the final finding_count before we read it.
"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import LiveFeed from "@/components/live-feed";
import FindingsList from "@/components/findings-list";

const API_BASE = "http://localhost:8000";

interface RunSummary {
  id: string;
  repo_id: string;
  status: string;
  finding_count: number;
  created_at: string;
}

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-zinc-500/15 text-zinc-400",
  scanning: "bg-teal-500/15 text-teal-400 animate-pulse",
  completed: "bg-green-500/15 text-green-400",
  failed: "bg-red-500/15 text-red-400",
};

export default function RunPage() {
  const { run_id } = useParams<{ run_id: string }>();
  const [run, setRun] = useState<RunSummary | null>(null);
  const [showFindings, setShowFindings] = useState(false);

  const fetchRun = useCallback(async () => {
    const res = await fetch(`${API_BASE}/api/runs/${run_id}`, {
      cache: "no-store",
    });
    if (res.ok) {
      const data: RunSummary = await res.json();
      setRun(data);
      if (data.status === "completed" || data.status === "failed") {
        setShowFindings(true);
      }
    }
  }, [run_id]);

  useEffect(() => {
    fetchRun();
  }, [fetchRun]);

  const handleRunComplete = useCallback(() => {
    setTimeout(fetchRun, 500);
  }, [fetchRun]);

  if (!run) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <p className="text-zinc-500">Loading run...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 font-sans">
      <main className="mx-auto max-w-4xl px-6 py-12">
        <Link
          href="/"
          className="mb-6 inline-block text-sm text-zinc-500 transition-colors hover:text-zinc-300"
        >
          &larr; Back to repos
        </Link>

        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">
              Audit Run
            </h1>
            <p className="mt-1 font-mono text-xs text-zinc-500">
              {run.id}
            </p>
          </div>
          <div className="flex items-center gap-4">
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold uppercase ${
                STATUS_STYLES[run.status] ?? STATUS_STYLES.pending
              }`}
            >
              {run.status}
            </span>
            {run.finding_count > 0 && (
              <span className="text-sm text-zinc-400">
                {run.finding_count} finding{run.finding_count !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>

        <LiveFeed runId={run_id} onRunComplete={handleRunComplete} />

        {showFindings && (
          <div className="mt-8">
            <FindingsList runId={run_id} />
          </div>
        )}

        {run.status === "completed" && (
          <div className="mt-8 flex gap-3">
            <a
              href={`${API_BASE}/api/runs/${run_id}/export?format=html`}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-800"
            >
              Download HTML Report
            </a>
            <a
              href={`${API_BASE}/api/runs/${run_id}/export?format=zip`}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-800"
            >
              Download ZIP Bundle
            </a>
          </div>
        )}
      </main>
    </div>
  );
}
