// RepoCards — client component for the repo picker.
//
// Manages two pieces of state: which card is selected and whether a run is
// being started. The "Start Audit" button is disabled until a card is selected
// and stays disabled while the POST /api/runs request is in flight, preventing
// accidental double-submissions.
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface Repo {
  id: string;
  name: string;
  description: string;
  language: string;
  path: string;
}

const LANGUAGE_COLORS: Record<string, string> = {
  javascript: "bg-yellow-400",
  typescript: "bg-blue-500",
  python: "bg-green-500",
  go: "bg-cyan-500",
  rust: "bg-orange-500",
};

const API_BASE = "http://localhost:8000";

export default function RepoCards({ repos }: { repos: Repo[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const router = useRouter();

  async function handleStartAudit() {
    if (!selectedId || starting) return;
    setStarting(true);
    try {
      const res = await fetch(`${API_BASE}/api/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_id: selectedId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }));
        alert(`Failed to start audit: ${err.detail}`);
        return;
      }
      const run: { id: string } = await res.json();
      router.push(`/runs/${run.id}`);
    } catch {
      alert("Could not reach the backend. Is the server running?");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {repos.map((repo) => {
          const isSelected = selectedId === repo.id;
          return (
            <button
              key={repo.id}
              onClick={() => setSelectedId(isSelected ? null : repo.id)}
              className={`flex flex-col items-start gap-3 rounded-lg border p-5 text-left transition-all ${
                isSelected
                  ? "border-blue-500 bg-blue-50 ring-2 ring-blue-500 dark:bg-blue-950"
                  : "border-zinc-200 bg-white hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700 dark:hover:bg-zinc-800"
              }`}
            >
              <div className="flex w-full items-center justify-between">
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                  {repo.name}
                </h2>
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium text-white ${
                    LANGUAGE_COLORS[repo.language.toLowerCase()] ?? "bg-zinc-500"
                  }`}
                >
                  {repo.language}
                </span>
              </div>
              <p className="text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                {repo.description}
              </p>
              <span className="font-mono text-xs text-zinc-400 dark:text-zinc-500">
                {repo.path}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-6 flex justify-end">
        <button
          onClick={handleStartAudit}
          disabled={!selectedId || starting}
          className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {starting ? "Starting..." : "Start Audit"}
        </button>
      </div>
    </div>
  );
}
