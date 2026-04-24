// Colored pill showing where a run or patch currently stands.
import { cn } from "@/lib/utils"

export type AuditStatus = "scanning" | "patching" | "reviewing" | "complete" | "failed"

interface StatusBadgeProps {
  status: AuditStatus
  className?: string
}

const statusConfig = {
  scanning: {
    label: "Scanning",
    className: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
    pulse: true,
  },
  patching: {
    label: "Patching",
    className: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    pulse: true,
  },
  reviewing: {
    label: "Reviewing",
    className: "bg-violet-400/10 text-violet-400 border-violet-400/20",
    pulse: true,
  },
  complete: {
    label: "Complete",
    className: "bg-green-500/10 text-green-400 border-green-500/20",
    pulse: false,
  },
  failed: {
    label: "Failed",
    className: "bg-red-500/10 text-red-400 border-red-500/20",
    pulse: false,
  },
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status]

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
        config.className,
        className
      )}
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          status === "scanning" && "bg-cyan-400",
          status === "patching" && "bg-amber-400",
          status === "reviewing" && "bg-violet-400",
          status === "complete" && "bg-green-400",
          status === "failed" && "bg-red-400",
          config.pulse && "animate-pulse"
        )}
      />
      {config.label}
    </span>
  )
}
