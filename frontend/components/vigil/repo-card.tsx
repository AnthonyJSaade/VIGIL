// Tile for a single demo repo on the landing page.
"use client"

import { cn } from "@/lib/utils"
import type { Repository } from "@/lib/api"
import { GitBranch } from "lucide-react"

interface RepoCardProps {
  repo: Repository
  selected?: boolean
  onSelect?: (repo: Repository) => void
}

const languageColors: Record<string, string> = {
  TypeScript: "bg-blue-500",
  JavaScript: "bg-yellow-500",
  Python: "bg-green-500",
  Go: "bg-cyan-500",
  Rust: "bg-orange-500",
  Java: "bg-red-500",
}

export function RepoCard({ repo, selected, onSelect }: RepoCardProps) {
  return (
    <button
      onClick={() => onSelect?.(repo)}
      className={cn(
        "group relative w-full rounded-lg border bg-card p-5 text-left transition-all",
        "hover:border-primary/50 hover:bg-card/80",
        selected
          ? "border-primary ring-2 ring-primary/20"
          : "border-border"
      )}
    >
      {selected && (
        <div className="absolute right-3 top-3 h-2.5 w-2.5 rounded-full bg-primary" />
      )}

      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
          <GitBranch className="h-5 w-5 text-muted-foreground" />
        </div>

        <div className="flex-1 min-w-0">
          <span className="font-medium text-foreground truncate block">{repo.name}</span>

          <p className="mt-1.5 text-sm text-muted-foreground line-clamp-2">
            {repo.description}
          </p>

          <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className={cn("h-2.5 w-2.5 rounded-full", languageColors[repo.language] || "bg-gray-500")} />
              {repo.language}
            </span>
          </div>
        </div>
      </div>
    </button>
  )
}
