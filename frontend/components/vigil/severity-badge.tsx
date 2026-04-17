import { cn } from "@/lib/utils"
import { AlertCircle, AlertTriangle, Info } from "lucide-react"

export type Severity = "error" | "warning" | "info"

interface SeverityBadgeProps {
  severity: Severity
  className?: string
}

const severityConfig = {
  error: {
    label: "Error",
    icon: AlertCircle,
    className: "bg-red-500/10 text-red-400 border-red-500/20",
  },
  warning: {
    label: "Warning",
    icon: AlertTriangle,
    className: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  },
  info: {
    label: "Info",
    icon: Info,
    className: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  },
}

export function SeverityBadge({ severity, className }: SeverityBadgeProps) {
  const config = severityConfig[severity]
  const Icon = config.icon

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        config.className,
        className
      )}
    >
      <Icon className="h-3 w-3" />
      {config.label}
    </span>
  )
}
