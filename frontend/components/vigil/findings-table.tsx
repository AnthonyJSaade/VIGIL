// Table of findings for a run. Click a row to open the detail page.
"use client"

import { useRouter } from "next/navigation"
import { cn } from "@/lib/utils"
import { SeverityBadge } from "./severity-badge"
import { ConfidenceBar } from "./confidence-bar"
import type { Finding } from "@/lib/api"
import { FileCode, ChevronRight } from "lucide-react"

interface FindingsTableProps {
  findings: Finding[]
  auditId: string
  className?: string
}

export function FindingsTable({ findings, auditId, className }: FindingsTableProps) {
  const router = useRouter()

  return (
    <div className={cn("rounded-lg border border-border bg-card overflow-hidden", className)}>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground">Severity</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground">Rule ID</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground">File</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground">Line</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground">Scanner</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground">Confidence</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {findings.map((finding) => (
              <tr
                key={finding.id}
                onClick={() => router.push(`/audit/${auditId}/finding/${finding.id}`)}
                className="border-b border-border/50 transition-colors hover:bg-muted/20 cursor-pointer"
              >
                <td className="px-4 py-3">
                  <SeverityBadge severity={finding.severity} />
                </td>
                <td className="px-4 py-3">
                  <code className="text-xs text-foreground font-mono">
                    {finding.ruleId.split(".").pop()}
                  </code>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <FileCode className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm text-foreground truncate max-w-[180px]">
                      {finding.filePath}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className="text-sm text-muted-foreground font-mono">
                    {finding.startLine}
                    {finding.endLine !== finding.startLine && `-${finding.endLine}`}
                  </span>
                </td>
                <td className="px-4 py-3">
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
                </td>
                <td className="px-4 py-3">
                  <ConfidenceBar value={finding.confidence} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-center rounded-md p-1.5 text-muted-foreground">
                    <ChevronRight className="h-4 w-4" />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
