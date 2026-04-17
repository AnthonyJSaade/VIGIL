"use client"

import { useState, useCallback, useEffect, useRef } from "react"
import { Scissors, Eye, ShieldCheck, Loader2, CheckCircle2, XCircle, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { AgentCard } from "./agent-card"
import { DiffBlock } from "./code-block"
import { cn } from "@/lib/utils"
import {
  requestPatch,
  fetchPatches,
  requestVerify,
  fetchVerification,
  type PatchWithVerdict,
  type VerificationReport,
} from "@/lib/api"

type PipelineStage = "idle" | "patching" | "reviewing" | "awaiting-verify" | "verifying" | "done" | "error"

interface PatchPipelineProps {
  findingId: string
  auditId: string
}

export function PatchPipeline({ findingId }: PatchPipelineProps) {
  const [stage, setStage] = useState<PipelineStage>("idle")
  const [attempts, setAttempts] = useState<PatchWithVerdict[]>([])
  const [verification, setVerification] = useState<VerificationReport | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => () => clearPoll(), [clearPoll])

  // Load existing patches on mount (in case user already triggered a patch)
  useEffect(() => {
    fetchPatches(findingId)
      .then(async (data) => {
        if (data.length === 0) return
        setAttempts(data)
        const last = data[data.length - 1]
        const approved = data.find((d) => d.verdict?.approved)

        if (approved) {
          const report = await fetchVerification(approved.patch.id).catch(() => null)
          if (report) {
            setVerification(report)
            setStage("done")
          } else {
            setStage("awaiting-verify")
          }
        } else if (last.verdict) {
          setStage("done")
        }
      })
      .catch(() => {})
  }, [findingId])

  const pollPatches = useCallback(
    (knownAttemptIds: Set<string>) => {
      clearPoll()
      pollRef.current = setInterval(async () => {
        try {
          const data = await fetchPatches(findingId)
          if (data.length === 0) return

          setAttempts(data)
          const last = data[data.length - 1]

          // When forcing a retry, we only care about attempts created *after*
          // we triggered the new run — otherwise we'd immediately "find" the
          // old verdict and exit. Wait for at least one brand-new row.
          const freshAttempt = data.find((d) => !knownAttemptIds.has(d.patch.id))
          if (!freshAttempt) return

          if (freshAttempt.verdict) {
            if (last.verdict) {
              clearPoll()
              if (last.verdict.approved) {
                setStage("awaiting-verify")
              } else {
                const stillWaiting = data.some((d) => !d.verdict)
                setStage(stillWaiting ? "reviewing" : "done")
              }
            }
          } else {
            setStage("reviewing")
          }
        } catch {
          /* keep polling */
        }
      }, 2000)
    },
    [findingId, clearPoll],
  )

  const startPatch = useCallback(
    async (opts?: { force?: boolean }) => {
      const force = !!opts?.force
      const knownAttemptIds = new Set(attempts.map((a) => a.patch.id))

      setStage("patching")
      setErrorMsg(null)
      if (force) {
        setVerification(null)
      }

      try {
        await requestPatch(findingId, { force })
      } catch {
        setErrorMsg("Failed to request patch. Is the backend running?")
        setStage("error")
        return
      }

      pollPatches(knownAttemptIds)
    },
    [findingId, attempts, pollPatches],
  )

  const startVerify = useCallback(
    async (opts?: { force?: boolean }) => {
      const approved = attempts.find((a) => a.verdict?.approved)
      if (!approved) return

      const force = !!opts?.force
      setStage("verifying")
      setErrorMsg(null)
      if (force) {
        setVerification(null)
      }

      try {
        await requestVerify(approved.patch.id, { force })
      } catch {
        setErrorMsg("Failed to start verification.")
        setStage("error")
        return
      }

      clearPoll()
      pollRef.current = setInterval(async () => {
        try {
          const result = await fetchVerification(approved.patch.id)
          if (result) {
            clearPoll()
            setVerification(result)
            setStage("done")
          }
        } catch {
          /* keep polling */
        }
      }, 2000)
    },
    [attempts, clearPoll],
  )

  const latestApproved = attempts.find((a) => a.verdict?.approved)
  const latestRejected = attempts.filter((a) => a.verdict && !a.verdict.approved)
  const hasApproval = !!latestApproved

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-medium text-foreground flex items-center gap-2">
        Patch &amp; Review Pipeline
      </h2>

      {/* Step indicators */}
      <div className="flex items-center gap-2 text-xs">
        <StepIndicator label="Surgeon" active={stage === "patching"} done={attempts.length > 0} icon={Scissors} color="amber" />
        <div className="h-px w-8 bg-border" />
        <StepIndicator label="Critic" active={stage === "reviewing"} done={attempts.some((a) => !!a.verdict)} icon={Eye} color="violet" />
        <div className="h-px w-8 bg-border" />
        <StepIndicator label="Verifier" active={stage === "verifying"} done={!!verification} icon={ShieldCheck} color="green" />
      </div>

      {/* Idle state */}
      {stage === "idle" && attempts.length === 0 && (
        <div className="rounded-lg border border-border bg-card p-6 text-center">
          <p className="text-sm text-muted-foreground mb-4">
            Ready to generate a minimal patch for this vulnerability.
          </p>
          <Button onClick={() => startPatch()} className="gap-2 bg-amber-500 text-amber-950 hover:bg-amber-400">
            <Scissors className="h-4 w-4" />
            Request Patch
          </Button>
        </div>
      )}

      {/* Patching */}
      {stage === "patching" && (
        <AgentCard agent="surgeon">
          <div className="flex items-center gap-3">
            <Loader2 className="h-4 w-4 animate-spin text-amber-400" />
            <span className="text-sm">Surgeon is generating a minimal patch...</span>
          </div>
        </AgentCard>
      )}

      {/* Show all attempts */}
      {attempts.map((attempt, idx) => (
        <div key={attempt.patch.id} className="space-y-3">
          <AgentCard agent="surgeon">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted-foreground">
                Attempt {attempt.patch.attempt}
                {attempt.patch.priorConcerns && attempt.patch.priorConcerns.length > 0 && " (retry)"}
              </span>
            </div>
            {attempt.patch.explanation && (
              <p className="text-sm text-muted-foreground mb-3">{attempt.patch.explanation}</p>
            )}
            <DiffBlock diff={attempt.patch.diff} />
          </AgentCard>

          {attempt.verdict && (
            <AgentCard agent="critic">
              <div className="flex items-center gap-2 mb-2">
                {attempt.verdict.approved ? (
                  <CheckCircle2 className="h-4 w-4 text-green-400" />
                ) : (
                  <XCircle className="h-4 w-4 text-red-400" />
                )}
                <span className={cn("text-sm font-medium", attempt.verdict.approved ? "text-green-400" : "text-red-400")}>
                  {attempt.verdict.approved ? "Approved" : "Rejected"}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">{attempt.verdict.reasoning}</p>
              {attempt.verdict.concerns.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {attempt.verdict.concerns.map((c, i) => (
                    <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                      <span className="text-amber-400 mt-0.5">•</span> {c}
                    </li>
                  ))}
                </ul>
              )}
            </AgentCard>
          )}

          {/* If this is the last attempt and we're still reviewing */}
          {idx === attempts.length - 1 && stage === "reviewing" && !attempt.verdict && (
            <AgentCard agent="critic">
              <div className="flex items-center gap-3">
                <Loader2 className="h-4 w-4 animate-spin text-violet-400" />
                <span className="text-sm">Critic is reviewing the patch...</span>
              </div>
            </AgentCard>
          )}
        </div>
      ))}

      {/* Awaiting verify */}
      {stage === "awaiting-verify" && (
        <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-6 text-center">
          <CheckCircle2 className="h-8 w-8 text-green-400 mx-auto mb-3" />
          <p className="text-sm text-foreground mb-4">
            Critic approved the patch. Ready to verify in a sandbox copy.
          </p>
          <Button onClick={() => startVerify()} className="gap-2 bg-green-600 text-white hover:bg-green-500">
            <ShieldCheck className="h-4 w-4" />
            Verify in Sandbox
          </Button>
        </div>
      )}

      {/* Verifying */}
      {stage === "verifying" && (
        <AgentCard agent="verifier">
          <div className="flex items-center gap-3">
            <Loader2 className="h-4 w-4 animate-spin text-green-400" />
            <span className="text-sm">Running verification in sandbox...</span>
          </div>
        </AgentCard>
      )}

      {/* Verification result */}
      {verification && (
        <AgentCard agent="verifier">
          <div className="flex items-center gap-2 mb-2">
            {verification.scannerRerunClean ? (
              <CheckCircle2 className="h-4 w-4 text-green-400" />
            ) : (
              <XCircle className="h-4 w-4 text-red-400" />
            )}
            <span className={cn("text-sm font-medium", verification.scannerRerunClean ? "text-green-400" : "text-red-400")}>
              Scanner rerun: {verification.scannerRerunClean ? "Clean" : "Still flagged"}
            </span>
          </div>
          {verification.testsPassed !== null && (
            <p className="text-xs text-muted-foreground">
              Tests: {verification.testsPassed ? "Passed" : "Failed"}
            </p>
          )}
          <pre className="text-xs text-muted-foreground mt-2 whitespace-pre-wrap font-mono">
            {verification.details}
          </pre>
        </AgentCard>
      )}

      {/* Verification failed — offer both retry paths */}
      {verification && !verification.scannerRerunClean && stage === "done" && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-6 space-y-3">
          <p className="text-sm text-foreground text-center">
            Verification failed. Choose a retry path:
          </p>
          <div className="flex gap-3 justify-center flex-wrap">
            <Button
              onClick={() => startPatch({ force: true })}
              variant="outline"
              className="gap-2"
            >
              <Scissors className="h-4 w-4" />
              Regenerate Patch
            </Button>
            <Button
              onClick={() => startVerify({ force: true })}
              variant="outline"
              className="gap-2"
            >
              <RefreshCw className="h-4 w-4" />
              Re-run Verification
            </Button>
          </div>
        </div>
      )}

      {/* Done without approval (all rejected) */}
      {stage === "done" && !hasApproval && !verification && latestRejected.length > 0 && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-6 text-center">
          <XCircle className="h-8 w-8 text-red-400 mx-auto mb-3" />
          <p className="text-sm text-foreground mb-4">
            All patch attempts were rejected by the Critic.
          </p>
          <Button onClick={() => startPatch({ force: true })} variant="outline" className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Try Again
          </Button>
        </div>
      )}

      {/* Error */}
      {stage === "error" && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
          <p className="text-sm text-destructive font-medium">{errorMsg}</p>
          <Button
            onClick={() => startPatch({ force: attempts.length > 0 })}
            variant="outline"
            size="sm"
            className="mt-3 gap-2"
          >
            <RefreshCw className="h-4 w-4" />
            Retry
          </Button>
        </div>
      )}
    </div>
  )
}

function StepIndicator({
  label,
  active,
  done,
  icon: Icon,
  color,
}: {
  label: string
  active: boolean
  done: boolean
  icon: React.ElementType
  color: string
}) {
  const colorClasses: Record<string, { bg: string; text: string; border: string }> = {
    amber: { bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/30" },
    violet: { bg: "bg-violet-400/10", text: "text-violet-400", border: "border-violet-400/30" },
    green: { bg: "bg-green-500/10", text: "text-green-400", border: "border-green-500/30" },
  }
  const c = colorClasses[color] || colorClasses.amber

  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-full border px-3 py-1",
        active ? `${c.bg} ${c.border}` : done ? `${c.bg} ${c.border}` : "border-border bg-muted/30"
      )}
    >
      {active ? (
        <Loader2 className={cn("h-3 w-3 animate-spin", c.text)} />
      ) : done ? (
        <CheckCircle2 className={cn("h-3 w-3", c.text)} />
      ) : (
        <Icon className="h-3 w-3 text-muted-foreground" />
      )}
      <span className={cn("text-xs font-medium", active || done ? c.text : "text-muted-foreground")}>{label}</span>
    </div>
  )
}
