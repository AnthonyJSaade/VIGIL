// Compact summary tile (icon + number + label) used in the dashboard header.
import { cn } from "@/lib/utils"
import type { LucideIcon } from "lucide-react"

interface StatCardProps {
  label: string
  value: number | string
  icon: LucideIcon
  variant?: "default" | "error" | "warning" | "info"
  className?: string
}

const variantStyles = {
  default: {
    icon: "text-foreground",
    bg: "bg-muted",
  },
  error: {
    icon: "text-red-400",
    bg: "bg-red-500/10",
  },
  warning: {
    icon: "text-amber-400",
    bg: "bg-amber-500/10",
  },
  info: {
    icon: "text-blue-400",
    bg: "bg-blue-500/10",
  },
}

export function StatCard({ label, value, icon: Icon, variant = "default", className }: StatCardProps) {
  const styles = variantStyles[variant]

  return (
    <div className={cn("rounded-lg border border-border bg-card p-4", className)}>
      <div className="flex items-center gap-3">
        <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg", styles.bg)}>
          <Icon className={cn("h-5 w-5", styles.icon)} />
        </div>
        <div>
          <p className="text-2xl font-semibold text-foreground">{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </div>
    </div>
  )
}
