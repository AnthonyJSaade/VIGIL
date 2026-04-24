// Audit dashboard: live SSE timeline of agent events plus the findings list for one run.
"use client"

import { use, useState, useEffect, useCallback, useRef } from "react"
import Link from "next/link"
import { Shield, ArrowLeft, Search, AlertCircle, AlertTriangle, Info, FileText, FileArchive, Wrench, Sparkles, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/vigil/status-badge"
import { StatCard } from "@/components/vigil/stat-card"
import { FindingsTable } from "@/components/vigil/findings-table"
import { AgentTimeline, type TimelineEvent } from "@/components/vigil/agent-timeline"
import { fetchRun, fetchFindings, sseUrl, exportUrl, triggerLlmReview, type RunSummary, type Finding } from "@/lib/api"

interface AuditPageProps {
  params: Promise<{ id: string }>
}

type LlmStage = "not-started" | "running" | "done" | "error"

function actionToLabel(action: string): string {
  return action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

function payloadToDetails(payload: Record<string, unknown>): string | undefined {
  if (payload.message) return String(payload.message)
  if (payload.file_path) return String(payload.file_path)
  if (payload.finding_count !== undefined) return `${payload.finding_count} findings`
  if (payload.error) return String(payload.error)
  const keys = Object.keys(payload).filter((k) => k !== "run_id")
  if (keys.length === 0) return undefined
  return keys.map((k) => `${k}: ${payload[k]}`).join(", ")
}

export default function AuditPage({ params }: AuditPageProps) {
  const { id: runId } = use(params)
  const [run, setRun] = useState<RunSummary | null>(null)
  const [findings, setFindings] = useState<Finding[]>([])
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [sseConnected, setSseConnected] = useState(false)
  const [semgrepDone, setSemgrepDone] = useState(false)
  const [llmStage, setLlmStage] = useState<LlmStage>("not-started")
  const [llmError, setLlmError] = useState<string | null>(null)
  const eventIdCounter = useRef(0)

  const loadRun = useCallback(async () => {
    try {
      const data = await fetchRun(runId)
      setRun(data)
      return data
    } catch {
      return null
    }
  }, [runId])

  const loadFindings = useCallback(async () => {
    try {
      const data = await fetchFindings(runId)
      setFindings(data)
    } catch { /* findings may not be ready yet */ }
  }, [runId])

  useEffect(() => {
    loadRun()
  }, [loadRun])

  // SSE stream
  useEffect(() => {
    const source = new EventSource(sseUrl(runId))
    setSseConnected(true)

    source.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data)
        const role = evt.role || "hunter"
        const action = evt.action || "unknown"
        const payload = evt.payload || {}
        const ts = evt.timestamp
          ? new Date(evt.timestamp).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
          : new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })

        eventIdCounter.current += 1
        const tlEvent: TimelineEvent = {
          id: `sse-${eventIdCounter.current}`,
          agent: role as TimelineEvent["agent"],
          action: actionToLabel(action),
          timestamp: ts,
          details: payloadToDetails(payload),
        }
        setEvents((prev) => [...prev, tlEvent])

        // Phase 1 (Semgrep) done — show findings right away.
        if (action === "scan_completed" && payload.phase === "semgrep") {
          setSemgrepDone(true)
          setTimeout(() => {
            loadRun()
            loadFindings()
          }, 300)
        }

        // LLM phase lifecycle.
        if (action === "llm_review_started") {
          setLlmStage("running")
        }
        if (action === "llm_review_completed") {
          if (payload.error) {
            setLlmStage("error")
            setLlmError(String(payload.error))
          } else {
            setLlmStage("done")
          }
          setTimeout(() => {
            loadRun()
            loadFindings()
          }, 300)
        }
      } catch { /* ignore malformed */ }
    }

    source.onerror = () => {
      setSseConnected(false)
      source.close()
      loadRun().then((r) => {
        if (r && (r.status === "completed" || r.status === "failed")) {
          loadFindings()
        }
      })
    }

    return () => source.close()
  }, [runId, loadRun, loadFindings])

  // If page loads after scan already finished, hydrate findings + stage.
  useEffect(() => {
    if (!run) return
    if ((run.status === "completed" || run.status === "failed") && findings.length === 0) {
      loadFindings()
    }
    if (run.status === "completed" || run.status === "failed") {
      setSemgrepDone(true)
    }
  }, [run, findings.length, loadFindings])

  const startLlmReview = useCallback(async () => {
    setLlmStage("running")
    setLlmError(null)
    try {
      await triggerLlmReview(runId)
    } catch (e) {
      setLlmStage("error")
      setLlmError(e instanceof Error ? e.message : "Failed to start LLM review")
    }
  }, [runId])

  if (!run) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
      </div>
    )
  }

  const stats = {
    total: findings.length,
    errors: findings.filter((f) => f.severity === "error").length,
    warnings: findings.filter((f) => f.severity === "warning").length,
    info: findings.filter((f) => f.severity === "info").length,
  }
  const llmFindings = findings.filter((f) => f.scanner !== "semgrep").length

  const statusMap: Record<string, "scanning" | "complete" | "failed" | "reviewing"> = {
    pending: "scanning",
    scanning: "scanning",
    completed: "complete",
    failed: "failed",
  }

  const deepScanButton =
    semgrepDone && run.status !== "failed" ? (
      llmStage === "running" ? (
        <div className="flex items-center gap-2 text-xs text-violet-300">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Claude is reviewing the code…
        </div>
      ) : llmStage === "done" ? (
        <div className="text-xs text-violet-300/80">
          AI deep scan complete ({llmFindings} additional finding{llmFindings === 1 ? "" : "s"})
        </div>
      ) : llmStage === "error" ? (
        <div className="space-y-2">
          <p className="text-xs text-destructive">AI deep scan failed: {llmError}</p>
          <Button size="sm" variant="outline" className="gap-2" onClick={startLlmReview}>
            <Sparkles className="h-3.5 w-3.5" />
            Retry
          </Button>
        </div>
      ) : (
        <Button size="sm" variant="outline" className="gap-2" onClick={startLlmReview}>
          <Sparkles className="h-3.5 w-3.5 text-violet-400" />
          Run AI Deep Scan
        </Button>
      )
    ) : null

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-border/50 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              <span className="font-semibold text-foreground">VIGIL</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm font-medium text-foreground">{run.repoId}</p>
              <p className="text-xs text-muted-foreground font-mono">{run.id.slice(0, 12)}</p>
            </div>
            <StatusBadge status={statusMap[run.status] || "scanning"} />
          </div>
        </div>
      </header>

      <div className="flex-1 flex">
        {/* Left Sidebar - Agent Timeline */}
        <aside className="w-80 border-r border-border/50 bg-sidebar flex flex-col">
          <div className="p-4 border-b border-border/50">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-foreground">Agent Trace Timeline</h2>
              <span className={`h-2 w-2 rounded-full ${sseConnected ? "bg-green-400 animate-pulse" : "bg-muted-foreground"}`} />
            </div>
            <p className="text-xs text-muted-foreground mt-1">Real-time activity from agents</p>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {events.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <div className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent animate-spin mb-4" />
                <p className="text-sm text-muted-foreground">Waiting for agent events...</p>
              </div>
            ) : (
              <AgentTimeline events={events} actionSlot={deepScanButton} />
            )}
          </div>
        </aside>

        {/* Right Content Area */}
        <main className="flex-1 overflow-y-auto">
          <div className="p-6 space-y-6">
            {/* Phase Indicator */}
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 rounded-full px-3 py-1.5 bg-cyan-500/10 border border-cyan-500/20">
                <div className={`h-2 w-2 rounded-full ${!semgrepDone ? "bg-cyan-400 animate-pulse" : "bg-cyan-400"}`} />
                <span className="text-xs font-medium text-cyan-400">
                  {!semgrepDone && run.status !== "failed" && "Running Semgrep…"}
                  {semgrepDone && llmStage === "not-started" && "Semgrep complete"}
                  {llmStage === "running" && "AI deep scan running…"}
                  {llmStage === "done" && "Scan complete"}
                  {run.status === "failed" && "Scan failed"}
                </span>
              </div>
              {semgrepDone && llmStage !== "running" && (
                <div className="hidden md:block">
                  {llmStage === "not-started" ? (
                    <Button size="sm" variant="outline" className="gap-2" onClick={startLlmReview}>
                      <Sparkles className="h-3.5 w-3.5 text-violet-400" />
                      Run AI Deep Scan
                    </Button>
                  ) : llmStage === "error" ? (
                    <Button size="sm" variant="outline" className="gap-2" onClick={startLlmReview}>
                      <Sparkles className="h-3.5 w-3.5 text-violet-400" />
                      Retry AI Deep Scan
                    </Button>
                  ) : null}
                </div>
              )}
              {llmStage === "running" && (
                <div className="hidden md:flex items-center gap-2 text-xs text-violet-300">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Claude is reviewing the code…
                </div>
              )}
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-4 gap-4">
              <StatCard label="Total Findings" value={stats.total} icon={Search} />
              <StatCard label="Errors" value={stats.errors} icon={AlertCircle} variant="error" />
              <StatCard label="Warnings" value={stats.warnings} icon={AlertTriangle} variant="warning" />
              <StatCard label="Info" value={stats.info} icon={Info} variant="info" />
            </div>

            {/* Findings Section */}
            {findings.length > 0 && (
              <section>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-medium text-foreground">Findings</h2>
                  <div className="flex items-center gap-2">
                    <a href={exportUrl(runId, "html")} download>
                      <Button variant="outline" size="sm" className="gap-2">
                        <FileText className="h-4 w-4" />HTML Report
                      </Button>
                    </a>
                    <a href={exportUrl(runId, "zip")} download>
                      <Button variant="outline" size="sm" className="gap-2">
                        <FileArchive className="h-4 w-4" />ZIP Bundle
                      </Button>
                    </a>
                    <Link href={`/audit/${runId}/patch-all`}>
                      <Button size="sm" className="gap-2 bg-amber-500 text-amber-950 hover:bg-amber-400" disabled={!semgrepDone}>
                        <Wrench className="h-4 w-4" />Patch All Findings
                      </Button>
                    </Link>
                  </div>
                </div>
                <FindingsTable findings={findings} auditId={runId} />
              </section>
            )}

            {run.status === "failed" && (
              <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
                <p className="text-sm font-medium text-destructive">Scan failed</p>
                <p className="text-xs text-muted-foreground mt-1">Check the timeline for error details.</p>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
