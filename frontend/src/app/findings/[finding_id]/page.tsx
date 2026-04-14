// Finding detail page — shows a single finding in full and hosts the patch
// workflow.
//
// Sections:
//   • Header — severity badge, rule ID, AI Review tag (if Claude-sourced)
//   • Meta row — scanner name and confidence percentage
//   • Code snippet — vulnerable lines rendered with real line numbers
//   • PatchPanel — Surgeon → Critic → Verifier flow (see patch-panel.tsx)
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import SeverityBadge from "@/components/severity-badge";
import PatchPanel from "@/components/patch-panel";

const API_BASE = "http://localhost:8000";

interface FindingDetail {
  id: string;
  run_id: string;
  scanner: string;
  rule_id: string;
  severity: string;
  message: string;
  file_path: string;
  start_line: number;
  end_line: number;
  snippet: string;
  confidence: number;
  metadata: Record<string, unknown>;
  created_at: string;
}

export default function FindingDetailPage() {
  const { finding_id } = useParams<{ finding_id: string }>();
  const [finding, setFinding] = useState<FindingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      const res = await fetch(`${API_BASE}/api/findings/${finding_id}`, {
        cache: "no-store",
      });
      if (res.ok) {
        setFinding(await res.json());
      } else {
        setError("Finding not found.");
      }
    }
    load();
  }, [finding_id]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <p className="text-red-400">{error}</p>
      </div>
    );
  }

  if (!finding) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <p className="text-zinc-500">Loading finding...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 font-sans">
      <main className="mx-auto max-w-4xl px-6 py-12">
        <Link
          href={`/runs/${finding.run_id}`}
          className="mb-6 inline-block text-sm text-zinc-500 transition-colors hover:text-zinc-300"
        >
          &larr; Back to run
        </Link>

        <div className="mb-8">
          <div className="flex items-center gap-3">
            <SeverityBadge severity={finding.severity} />
            <span className="font-mono text-xs text-zinc-500">
              {finding.rule_id}
            </span>
            {finding.scanner === "claude-review" && (
              <span className="rounded-full bg-purple-500/15 px-2 py-0.5 text-xs font-semibold text-purple-400">
                AI Review
              </span>
            )}
          </div>
          <h1 className="mt-3 text-xl font-bold text-zinc-100">
            {finding.message}
          </h1>
          <p className="mt-2 font-mono text-sm text-zinc-400">
            {finding.file_path}:{finding.start_line}–{finding.end_line}
          </p>
        </div>

        <div className="mb-6 flex items-center gap-6 text-sm text-zinc-500">
          <div>
            <span className="text-zinc-600">Scanner: </span>
            <span className="text-zinc-300">{finding.scanner}</span>
          </div>
          <div>
            <span className="text-zinc-600">Confidence: </span>
            <span className="text-zinc-300">
              {(finding.confidence * 100).toFixed(0)}%
            </span>
          </div>
        </div>

        {finding.snippet && (
          <div className="mb-8">
            <h3 className="mb-2 text-sm font-semibold text-zinc-400">
              Vulnerable Code
            </h3>
            <pre className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900 p-4 font-mono text-xs leading-relaxed text-zinc-300">
              {finding.snippet.split("\n").map((line, i) => (
                <div key={i} className="flex">
                  <span className="mr-4 w-8 select-none text-right text-zinc-600">
                    {finding.start_line + i}
                  </span>
                  <span>{line}</span>
                </div>
              ))}
            </pre>
          </div>
        )}

        <div>
          <h3 className="mb-4 text-sm font-semibold text-zinc-400">
            Patch & Review
          </h3>
          <PatchPanel findingId={finding_id} />
        </div>
      </main>
    </div>
  );
}
