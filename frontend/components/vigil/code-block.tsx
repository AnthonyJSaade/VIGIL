// Syntax-highlighted code and diff viewer used across the app.
"use client"

import { cn } from "@/lib/utils"

interface CodeBlockProps {
  code: string
  language?: string
  startLine?: number
  highlightLines?: number[]
  className?: string
}

export function CodeBlock({
  code,
  language = "typescript",
  startLine = 1,
  highlightLines = [],
  className,
}: CodeBlockProps) {
  // Normalize line endings and strip a trailing blank line that would show an
  // empty row with just a line number. Keep internal blank lines intact.
  const normalized = code.replace(/\r\n/g, "\n").replace(/\n+$/, "")
  const lines = normalized.length > 0 ? normalized.split("\n") : [""]

  // Calculate width of the line-number gutter from the largest rendered number.
  const gutterWidth = String(startLine + lines.length - 1).length

  return (
    <div className={cn("overflow-hidden rounded-lg border border-border bg-[#0d0d12]", className)}>
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="text-xs text-muted-foreground">{language}</span>
      </div>
      <div className="overflow-x-auto">
        <pre className="p-4 text-sm leading-relaxed">
          <code>
            {lines.map((line, index) => {
              const lineNumber = startLine + index
              const isHighlighted = highlightLines.includes(lineNumber)

              return (
                <div
                  key={index}
                  className={cn(
                    "flex",
                    isHighlighted && "bg-red-500/10 -mx-4 px-4"
                  )}
                >
                  <span
                    className="mr-4 inline-block text-right text-muted-foreground/50 select-none shrink-0"
                    style={{ minWidth: `${gutterWidth}ch` }}
                  >
                    {lineNumber}
                  </span>
                  <span className="font-mono text-foreground/90 whitespace-pre">
                    {line === "" ? " " : line}
                  </span>
                </div>
              )
            })}
          </code>
        </pre>
      </div>
    </div>
  )
}

interface DiffBlockProps {
  diff: string
  className?: string
}

export function DiffBlock({ diff, className }: DiffBlockProps) {
  const lines = diff.split("\n")

  return (
    <div className={cn("overflow-hidden rounded-lg border border-border bg-[#0d0d12]", className)}>
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="text-xs text-muted-foreground">Unified Diff</span>
      </div>
      <div className="overflow-x-auto">
        <pre className="p-4 text-sm">
          <code>
            {lines.map((line, index) => {
              let lineClass = "text-foreground/70"
              
              if (line.startsWith("+") && !line.startsWith("+++")) {
                lineClass = "text-green-400 bg-green-500/10"
              } else if (line.startsWith("-") && !line.startsWith("---")) {
                lineClass = "text-red-400 bg-red-500/10"
              } else if (line.startsWith("@@")) {
                lineClass = "text-violet-400 bg-violet-500/10"
              } else if (line.startsWith("+++") || line.startsWith("---")) {
                lineClass = "text-muted-foreground"
              }

              return (
                <div
                  key={index}
                  className={cn("font-mono -mx-4 px-4", lineClass)}
                >
                  {line || " "}
                </div>
              )
            })}
          </code>
        </pre>
      </div>
    </div>
  )
}

interface SideBySideDiffProps {
  original: {
    code: string
    startLine: number
  }
  patched: {
    code: string
    startLine: number
  }
  fileName: string
  className?: string
}

export function SideBySideDiff({ original, patched, fileName, className }: SideBySideDiffProps) {
  const originalLines = original.code.split("\n")
  const patchedLines = patched.code.split("\n")
  const maxLines = Math.max(originalLines.length, patchedLines.length)

  const getLineClass = (originalLine: string, patchedLine: string, side: "original" | "patched") => {
    if (originalLine !== patchedLine) {
      return side === "original" 
        ? "bg-red-500/10 text-red-300" 
        : "bg-green-500/10 text-green-300"
    }
    return "text-foreground/80"
  }

  return (
    <div className={cn("overflow-hidden rounded-lg border border-border bg-[#0d0d12]", className)}>
      <div className="flex border-b border-border">
        <div className="flex-1 px-4 py-2 border-r border-border">
          <span className="text-xs text-red-400">Original</span>
          <span className="text-xs text-muted-foreground ml-2 font-mono">{fileName}</span>
        </div>
        <div className="flex-1 px-4 py-2">
          <span className="text-xs text-green-400">Patched</span>
          <span className="text-xs text-muted-foreground ml-2 font-mono">{fileName}</span>
        </div>
      </div>
      <div className="flex overflow-x-auto">
        {/* Original Side */}
        <div className="flex-1 border-r border-border min-w-0">
          <pre className="p-4 text-sm">
            <code>
              {Array.from({ length: maxLines }).map((_, index) => {
                const originalLine = originalLines[index] ?? ""
                const patchedLine = patchedLines[index] ?? ""
                const lineNumber = original.startLine + index
                
                return (
                  <div
                    key={`orig-${index}`}
                    className={cn(
                      "flex -mx-4 px-4",
                      getLineClass(originalLine, patchedLine, "original")
                    )}
                  >
                    <span className="mr-4 inline-block w-8 text-right text-muted-foreground/50 select-none shrink-0">
                      {lineNumber}
                    </span>
                    <span className="font-mono whitespace-pre">{originalLine || " "}</span>
                  </div>
                )
              })}
            </code>
          </pre>
        </div>
        
        {/* Patched Side */}
        <div className="flex-1 min-w-0">
          <pre className="p-4 text-sm">
            <code>
              {Array.from({ length: maxLines }).map((_, index) => {
                const originalLine = originalLines[index] ?? ""
                const patchedLine = patchedLines[index] ?? ""
                const lineNumber = patched.startLine + index
                
                return (
                  <div
                    key={`patch-${index}`}
                    className={cn(
                      "flex -mx-4 px-4",
                      getLineClass(originalLine, patchedLine, "patched")
                    )}
                  >
                    <span className="mr-4 inline-block w-8 text-right text-muted-foreground/50 select-none shrink-0">
                      {lineNumber}
                    </span>
                    <span className="font-mono whitespace-pre">{patchedLine || " "}</span>
                  </div>
                )
              })}
            </code>
          </pre>
        </div>
      </div>
    </div>
  )
}
