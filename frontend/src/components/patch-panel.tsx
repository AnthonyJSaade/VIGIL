// PatchPanel — Surgeon → Critic → Verifier workflow for a single finding.
//
// Flow:
//   1. "Request Patch" button → POST /api/findings/{id}/patch (202, background)
//   2. Poll GET /api/findings/{id}/patches every 2 s until results appear.
//   3. Render each patch attempt: unified diff + Critic verdict + concerns list.
//   4. If the latest patch is Critic-approved, show "Verify in Sandbox" button.
//   5. POST /api/patches/{id}/verify → poll GET /api/patches/{id}/verification.
//
// pollRef and verifyPollRef are refs (not state) so interval IDs survive
// re-renders without triggering extra effects. Both are cleared in a cleanup
// effect to avoid memory leaks if the user navigates away mid-poll.
"use client";

import { useState, useCallback, useRef, useEffect } from "react";

const API_BASE = "http://localhost:8000";

interface PatchResult {
  patch_id: string;
  finding_id: string;
  diff: string;
  explanation: string;
  attempt: number;
  approved: boolean;
  reasoning: string;
  concerns: string[];
}

interface VerificationResult {
  patch_id: string;
  scanner_rerun_clean: boolean;
  tests_passed: boolean | null;
  details: string;
}

function DiffViewer({ diff }: { diff: string }) {
  return (
    <pre className="overflow-x-auto rounded-md bg-zinc-900 p-3 text-xs leading-relaxed">
      {diff.split("\n").map((line, i) => {
        let color = "text-zinc-400";
        if (line.startsWith("+") && !line.startsWith("+++")) {
          color = "text-green-400";
        } else if (line.startsWith("-") && !line.startsWith("---")) {
          color = "text-red-400";
        } else if (line.startsWith("@@")) {
          color = "text-blue-400";
        }
        return (
          <div key={i} className={color}>
            {line}
          </div>
        );
      })}
    </pre>
  );
}

export default function PatchPanel({ findingId }: { findingId: string }) {
  const [patches, setPatches] = useState<PatchResult[]>([]);
  const [requesting, setRequesting] = useState(false);
  const [patchRequested, setPatchRequested] = useState(false);
  const [verification, setVerification] = useState<VerificationResult | null>(
    null
  );
  const [verifying, setVerifying] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const verifyPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** Fetch all patch attempts for this finding. Stops polling once the
   *  pipeline is done — either a patch was approved or all attempts exhausted. */
  const loadPatches = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_BASE}/api/findings/${findingId}/patches`,
        { cache: "no-store" }
      );
      if (res.ok) {
        const data: PatchResult[] = await res.json();
        setPatches(data);
        const pipelineDone =
          data.some((p) => p.approved) || data.length >= 2;
        if (pipelineDone && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    } catch {
      /* Network error — keep polling, backend may recover. */
    }
  }, [findingId]);

  useEffect(() => {
    loadPatches();
  }, [loadPatches]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (verifyPollRef.current) clearInterval(verifyPollRef.current);
    };
  }, []);

  // ── Surgeon trigger ──────────────────────────────────────────────────────

  /** POST the patch request, then start polling for results every 2 s. */
  async function handleRequestPatch() {
    if (requesting) return;
    setRequesting(true);
    setPatchRequested(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/findings/${findingId}/patch`,
        { method: "POST" }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }));
        alert(`Patch request failed: ${err.detail}`);
        setPatchRequested(false);
        return;
      }
      pollRef.current = setInterval(loadPatches, 2000);
    } catch {
      alert("Could not reach the backend.");
      setPatchRequested(false);
    } finally {
      setRequesting(false);
    }
  }

  // ── Sandbox verification trigger ─────────────────────────────────────────

  /** Kick off sandbox verification and poll until the result lands. */
  async function handleVerify(patchId: string) {
    if (verifying) return;
    setVerifying(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/patches/${patchId}/verify`,
        { method: "POST" }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }));
        alert(`Verification failed: ${err.detail}`);
        setVerifying(false);
        return;
      }
      verifyPollRef.current = setInterval(async () => {
        const vRes = await fetch(
          `${API_BASE}/api/patches/${patchId}/verification`,
          { cache: "no-store" }
        );
        if (vRes.ok) {
          const data: VerificationResult = await vRes.json();
          setVerification(data);
          setVerifying(false);
          if (verifyPollRef.current) {
            clearInterval(verifyPollRef.current);
            verifyPollRef.current = null;
          }
        }
      }, 2000);
    } catch {
      alert("Could not reach the backend.");
      setVerifying(false);
    }
  }

  if (patches.length === 0 && !patchRequested) {
    return (
      <button
        onClick={handleRequestPatch}
        disabled={requesting}
        className="rounded-lg bg-amber-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-700 disabled:opacity-40"
      >
        {requesting ? "Requesting..." : "Request Patch"}
      </button>
    );
  }

  if (patches.length === 0 && patchRequested) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-6 text-center">
        <div className="mb-2 text-sm text-zinc-400 animate-pulse">
          Surgeon is generating a patch...
        </div>
        <p className="text-xs text-zinc-600">
          The Surgeon–Critic pipeline is running. This usually takes 10–30
          seconds.
        </p>
      </div>
    );
  }

  // ── Render patch attempts ─────────────────────────────────────────────────
  // latestPatch drives the Verify button — only the most recent approved patch
  // is eligible, since earlier attempts were rejected by the Critic.
  const latestPatch = patches[patches.length - 1];

  return (
    <div className="space-y-6">
      {patches.map((p) => (
        <div
          key={p.patch_id}
          className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5"
        >
          <div className="mb-3 flex items-center justify-between">
            <h4 className="text-sm font-semibold text-zinc-200">
              Patch Attempt {p.attempt}
            </h4>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                p.approved
                  ? "bg-green-500/15 text-green-400"
                  : "bg-red-500/15 text-red-400"
              }`}
            >
              {p.approved ? "Approved" : "Rejected"}
            </span>
          </div>

          <DiffViewer diff={p.diff} />

          <div className="mt-4">
            <h5 className="mb-1 text-xs font-semibold uppercase text-zinc-500">
              Explanation
            </h5>
            <p className="text-sm text-zinc-300">{p.explanation}</p>
          </div>

          <div className="mt-4 rounded-md border border-zinc-800 bg-zinc-950 p-3">
            <h5 className="mb-1 text-xs font-semibold uppercase text-purple-400">
              Critic Verdict
            </h5>
            <p className="text-sm text-zinc-300">{p.reasoning}</p>
            {p.concerns.length > 0 && (
              <ul className="mt-2 space-y-1">
                {p.concerns.map((c, i) => (
                  <li key={i} className="text-xs text-zinc-500">
                    &bull; {c}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ))}

      {latestPatch.approved && !verification && (
        <button
          onClick={() => handleVerify(latestPatch.patch_id)}
          disabled={verifying}
          className="rounded-lg bg-green-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:opacity-40"
        >
          {verifying ? "Verifying in Sandbox..." : "Verify in Sandbox"}
        </button>
      )}

      {verification && (
        <div
          className={`rounded-lg border p-5 ${
            verification.scanner_rerun_clean
              ? "border-green-500/30 bg-green-500/5"
              : "border-red-500/30 bg-red-500/5"
          }`}
        >
          <h4 className="mb-3 text-sm font-semibold text-zinc-200">
            Verification Result
          </h4>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <span
                className={
                  verification.scanner_rerun_clean
                    ? "text-green-400"
                    : "text-red-400"
                }
              >
                {verification.scanner_rerun_clean ? "\u2713" : "\u2717"}
              </span>
              <span className="text-zinc-300">
                Scanner re-run:{" "}
                {verification.scanner_rerun_clean ? "Clean" : "Still flagged"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={
                  verification.tests_passed === null
                    ? "text-zinc-500"
                    : verification.tests_passed
                    ? "text-green-400"
                    : "text-red-400"
                }
              >
                {verification.tests_passed === null
                  ? "\u2014"
                  : verification.tests_passed
                  ? "\u2713"
                  : "\u2717"}
              </span>
              <span className="text-zinc-300">
                Tests:{" "}
                {verification.tests_passed === null
                  ? "Not configured"
                  : verification.tests_passed
                  ? "Passed"
                  : "Failed"}
              </span>
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              {verification.details}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
