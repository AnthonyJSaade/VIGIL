// Batch view: runs every finding in a run through the patch + verify pipeline in sequence.
"use client"

import { use, useState, useEffect, useRef, useCallback } from "react"
import Link from "next/link"
import { Shield, ArrowLeft, Wrench, Loader2, CheckCircle2, XCircle, ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { SeverityBadge } from "@/components/vigil/severity-badge"
import { AgentCard } from "@/components/vigil/agent-card"
import {
  fetchFindings,
  requestPatch,
  fetchPatches,
  requestVerify,
  fetchVerification,
  type Finding,
  type PatchWithVerdict,
  type VerificationReport,
} from "@/lib/api"

interface PatchAllPageProps {
  params: Promise<{ id: string }>
}

type FindingStatus = "pending" | "patching" | "reviewing" | "approved" | "rejected" | "verifying" | "verified" | "verify-failed" | "error"

interface FindingProgress {
  finding: Finding
  status: FindingStatus
  patch?: PatchWithVerdict
  verification?: VerificationReport
  error?: string
}

export default function PatchAllPage({ params }: PatchAllPageProps) {
  const { id: auditId } = use(params)
  const [findings, setFindings] = useState<Finding[]>([])
  const [progress, setProgress] = useState<FindingProgress[]>([])
  const [running, setRunning] = useState(false)
  const [complete, setComplete] = useState(false)
  const cancelRef = useRef(false)

  useEffect(() => {
    fetchFindings(auditId).then(setFindings).catch(() => {})
  }, [auditId])

  const updateProgress = useCallback((id: string, update: Partial<FindingProgress>) => {
    setProgress((prev) => prev.map((p) => (p.finding.id === id ? { ...p, ...update } : p)))
  }, [])

  const pollForPatches = useCallback(async (findingId: string): Promise<PatchWithVerdict | null> => {
    for (let i = 0; i < 60; i++) {
      if (cancelRef.current) return null
      await new Promise((r) => setTimeout(r, 2000))
      const data = await fetchPatches(findingId)
      const last = data[data.length - 1]
      if (last?.verdict) return last
    }
    return null
  }, [])

  const pollForVerification = useCallback(async (patchId: string): Promise<VerificationReport | null> => {
    for (let i = 0; i < 30; i++) {
      if (cancelRef.current) return null
      await new Promise((r) => setTimeout(r, 2000))
      const result = await fetchVerification(patchId)
      if (result) return result
    }
    return null
  }, [])

  const startBatch = useCallback(async () => {
    cancelRef.current = false
    setRunning(true)
    setComplete(false)

    const initial: FindingProgress[] = findings.map((f) => ({ finding: f, status: "pending" }))
    setProgress(initial)

    for (const finding of findings) {
      if (cancelRef.current) break

      updateProgress(finding.id, { status: "patching" })

      try {
        await requestPatch(finding.id)
        updateProgress(finding.id, { status: "reviewing" })

        const result = await pollForPatches(finding.id)
        if (!result) {
          updateProgress(finding.id, { status: "error", error: "Timeout waiting for patch" })
          continue
        }

        updateProgress(finding.id, { patch: result })

        if (result.verdict?.approved) {
          updateProgress(finding.id, { status: "verifying" })
          await requestVerify(result.patch.id)
          const vResult = await pollForVerification(result.patch.id)
          if (vResult) {
            updateProgress(finding.id, {
              status: vResult.scannerRerunClean ? "verified" : "verify-failed",
              verification: vResult,
            })
          } else {
            updateProgress(finding.id, { status: "error", error: "Verification timeout" })
          }
        } else {
          updateProgress(finding.id, { status: "rejected" })
        }
      } catch {
        updateProgress(finding.id, { status: "error", error: "Failed" })
      }
    }

    setRunning(false)
    setComplete(true)
  }, [findings, updateProgress, pollForPatches, pollForVerification])

  const doneCount = progress.filter((p) => !["pending", "patching", "reviewing", "verifying"].includes(p.status)).length
  const approvedCount = progress.filter((p) => p.status === "verified" || p.status === "approved" || p.status === "verify-failed").length
  const totalPercent = progress.length > 0 ? Math.round((doneCount / progress.length) * 100) : 0

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border/50 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href={`/audit/${auditId}`} className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              <span className="font-semibold text-foreground">VIGIL</span>
            </div>
            <span className="text-sm text-muted-foreground">/ Batch Patch</span>
          </div>
        </div>
      </header>

      <div className="flex-1 p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
                <Wrench className="h-5 w-5 text-amber-400" />
                Batch Patch All Findings
              </h1>
              <p className="text-sm text-muted-foreground mt-1">
                Process {findings.length} findings sequentially through the Surgeon → Critic → Verifier pipeline.
              </p>
            </div>
            {!running && !complete && (
              <Button
                onClick={startBatch}
                disabled={findings.length === 0}
                className="gap-2 bg-amber-500 text-amber-950 hover:bg-amber-400"
              >
                <Wrench className="h-4 w-4" />
                Start Batch
              </Button>
            )}
          </div>

          {/* Progress bar */}
          {progress.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Progress</span>
                <span className="text-foreground font-medium">
                  {doneCount}/{progress.length} ({totalPercent}%)
                </span>
              </div>
              <div className="h-2 rounded-full bg-muted overflow-hidden">
                <div className="h-full rounded-full bg-primary transition-all duration-300" style={{ width: `${totalPercent}%` }} />
              </div>
              <div className="flex gap-4 text-xs text-muted-foreground">
                <span>Approved: {approvedCount}</span>
                <span>Rejected: {progress.filter((p) => p.status === "rejected").length}</span>
                <span>Errors: {progress.filter((p) => p.status === "error").length}</span>
              </div>
            </div>
          )}

          {/* Finding list */}
          <div className="space-y-3">
            {progress.map((item) => (
              <FindingRow key={item.finding.id} item={item} auditId={auditId} />
            ))}
          </div>

          {complete && (
            <div className="text-center py-4">
              <Link href={`/audit/${auditId}`}>
                <Button variant="outline" className="gap-2">
                  <ArrowLeft className="h-4 w-4" />
                  Back to Audit
                </Button>
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function FindingRow({ item, auditId }: { item: FindingProgress; auditId: string }) {
  const statusIcons: Record<FindingStatus, React.ReactNode> = {
    pending: <div className="h-4 w-4 rounded-full border border-border" />,
    patching: <Loader2 className="h-4 w-4 animate-spin text-amber-400" />,
    reviewing: <Loader2 className="h-4 w-4 animate-spin text-violet-400" />,
    approved: <CheckCircle2 className="h-4 w-4 text-green-400" />,
    rejected: <XCircle className="h-4 w-4 text-red-400" />,
    verifying: <Loader2 className="h-4 w-4 animate-spin text-green-400" />,
    verified: <ShieldCheck className="h-4 w-4 text-green-400" />,
    "verify-failed": <XCircle className="h-4 w-4 text-amber-400" />,
    error: <XCircle className="h-4 w-4 text-destructive" />,
  }

  const statusLabels: Record<FindingStatus, string> = {
    pending: "Pending",
    patching: "Generating patch...",
    reviewing: "Critic reviewing...",
    approved: "Approved",
    rejected: "Rejected",
    verifying: "Verifying in sandbox...",
    verified: "Verified",
    "verify-failed": "Verification failed",
    error: item.error || "Error",
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-4">
        {statusIcons[item.status]}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <SeverityBadge severity={item.finding.severity} />
            <Link
              href={`/audit/${auditId}/finding/${item.finding.id}`}
              className="text-sm font-medium text-foreground hover:text-primary truncate"
            >
              {item.finding.ruleId}
            </Link>
          </div>
          <p className="text-xs text-muted-foreground mt-1 truncate">{item.finding.filePath}:{item.finding.startLine}</p>
        </div>
        <span className="text-xs text-muted-foreground whitespace-nowrap">{statusLabels[item.status]}</span>
      </div>

      {item.status === "verified" && item.verification && (
        <AgentCard agent="verifier" className="mt-3">
          <p className="text-xs text-green-400">Scanner rerun clean. Patch verified.</p>
        </AgentCard>
      )}
    </div>
  )
}
