import { cn } from "@/lib/utils"

interface ConfidenceBarProps {
  value: number // 0-100
  className?: string
}

export function ConfidenceBar({ value, className }: ConfidenceBarProps) {
  const clampedValue = Math.min(100, Math.max(0, value))
  
  let colorClass = "bg-red-500"
  if (clampedValue >= 80) {
    colorClass = "bg-green-500"
  } else if (clampedValue >= 60) {
    colorClass = "bg-cyan-500"
  } else if (clampedValue >= 40) {
    colorClass = "bg-amber-500"
  }

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all", colorClass)}
          style={{ width: `${clampedValue}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground">{clampedValue}%</span>
    </div>
  )
}
