// Finding detail page: shows the vulnerability and drives the Surgeon/Critic/Verifier pipeline.
"use client"

import { use, useState, useEffect } from "react"
import Link from "next/link"
import { Shield, ArrowLeft, FileCode, MapPin } from "lucide-react"
import { SeverityBadge } from "@/components/vigil/severity-badge"
import { ConfidenceBar } from "@/components/vigil/confidence-bar"
import { CodeBlock } from "@/components/vigil/code-block"
import { AgentCard } from "@/components/vigil/agent-card"
import { PatchPipeline } from "@/components/vigil/patch-pipeline"
import { fetchFinding, type Finding } from "@/lib/api"
import { cn } from "@/lib/utils"

interface FindingPageProps {
  params: Promise<{ id: string; findingId: string }>
}

export default function FindingPage({ params }: FindingPageProps) {
  const { id: auditId, findingId } = use(params)
  const [finding, setFinding] = useState<Finding | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetchFinding(findingId)
      .then(setFinding)
      .catch(() => setError(true))
  }, [findingId])

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-destructive font-medium">Finding not found</p>
          <Link href={`/audit/${auditId}`} className="text-xs text-primary hover:underline mt-2 block">
            Back to audit
          </Link>
        </div>
      </div>
    )
  }

  if (!finding) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
      </div>
    )
  }

  const fileExtension = finding.filePath.split(".").pop() || "text"
  const languageMap: Record<string, string> = {
    ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
    py: "python", go: "go", rs: "rust", java: "java", rb: "ruby",
    php: "php", c: "c", cpp: "cpp", cs: "csharp", swift: "swift",
    kt: "kotlin", yml: "yaml", yaml: "yaml", json: "json", md: "markdown",
    html: "html", css: "css", sql: "sql", sh: "bash",
  }
  const language = languageMap[fileExtension] || fileExtension

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-border/50 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href={`/audit/${auditId}`}
              className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              <span className="font-semibold text-foreground">VIGIL</span>
            </div>
            <span className="text-sm text-muted-foreground">/ Finding Detail</span>
          </div>
        </div>
      </header>

      <div className="flex-1 p-6">
        <div className="max-w-5xl mx-auto space-y-6">
          {/* Finding Header */}
          <div className="flex items-start justify-between">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <SeverityBadge severity={finding.severity} />
                <span
                  className={cn(
                    "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                    finding.scanner === "semgrep"
                      ? "bg-violet-500/10 text-violet-400 border border-violet-500/20"
                      : "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20"
                  )}
                >
                  {finding.scanner === "semgrep" ? "Semgrep" : "AI Review"}
                </span>
              </div>
              <h1 className="text-xl font-semibold text-foreground">{finding.ruleId}</h1>
              <p className="text-sm text-muted-foreground">{finding.message}</p>
            </div>
            <ConfidenceBar value={finding.confidence} />
          </div>

          {/* Location Info */}
          <div className="flex items-center gap-6 text-sm text-muted-foreground">
            <span className="flex items-center gap-2">
              <FileCode className="h-4 w-4" />
              <code className="font-mono">{finding.filePath}</code>
            </span>
            <span className="flex items-center gap-2">
              <MapPin className="h-4 w-4" />
              Lines {finding.startLine}
              {finding.endLine !== finding.startLine && `–${finding.endLine}`}
            </span>
          </div>

          {/* Vulnerable Code */}
          <AgentCard agent="hunter">
            <p className="mb-3 text-sm text-muted-foreground">Vulnerable code identified:</p>
            {finding.snippet && finding.snippet.trim().length > 0 ? (
              (() => {
                // Semgrep's `extra.lines` is usually just the matched line(s), which
                // can be fewer than end_line - start_line + 1. Scope the highlight
                // to what actually exists in the snippet so line numbering and
                // highlighting stay consistent.
                const snippetLineCount = finding.snippet.split("\n").length
                const highlightCount = Math.min(
                  snippetLineCount,
                  Math.max(1, finding.endLine - finding.startLine + 1),
                )
                const highlightLines = Array.from(
                  { length: highlightCount },
                  (_, i) => finding.startLine + i,
                )
                return (
                  <CodeBlock
                    code={finding.snippet}
                    language={language}
                    startLine={finding.startLine}
                    highlightLines={highlightLines}
                  />
                )
              })()
            ) : (
              <p className="rounded-md border border-border bg-muted/30 px-3 py-4 text-center text-xs text-muted-foreground">
                No code snippet was captured by the scanner.
                Open <code className="font-mono">{finding.filePath}</code> at line {finding.startLine} for context.
              </p>
            )}
          </AgentCard>

          {/* Patch Pipeline */}
          <PatchPipeline findingId={finding.id} auditId={auditId} />
        </div>
      </div>
    </div>
  )
}
