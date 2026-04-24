// Small tile for a single agent (Hunter, Surgeon, Critic, Verifier) with its current status.
"use client"

import { cn } from "@/lib/utils"
import { Crosshair, Scissors, Eye, ShieldCheck, type LucideIcon } from "lucide-react"

export type AgentType = "hunter" | "surgeon" | "critic" | "verifier"

interface AgentConfig {
  name: string
  icon: LucideIcon
  color: string
  borderColor: string
  bgColor: string
  textColor: string
}

export const agentConfigs: Record<AgentType, AgentConfig> = {
  hunter: {
    name: "Hunter",
    icon: Crosshair,
    color: "#06b6d4",
    borderColor: "border-l-cyan-500",
    bgColor: "bg-cyan-500/10",
    textColor: "text-cyan-400",
  },
  surgeon: {
    name: "Surgeon",
    icon: Scissors,
    color: "#f59e0b",
    borderColor: "border-l-amber-500",
    bgColor: "bg-amber-500/10",
    textColor: "text-amber-400",
  },
  critic: {
    name: "Critic",
    icon: Eye,
    color: "#a78bfa",
    borderColor: "border-l-violet-400",
    bgColor: "bg-violet-400/10",
    textColor: "text-violet-400",
  },
  verifier: {
    name: "Verifier",
    icon: ShieldCheck,
    color: "#22c55e",
    borderColor: "border-l-green-500",
    bgColor: "bg-green-500/10",
    textColor: "text-green-400",
  },
}

interface AgentCardProps {
  agent: AgentType
  children: React.ReactNode
  className?: string
}

export function AgentCard({ agent, children, className }: AgentCardProps) {
  const config = agentConfigs[agent]
  const Icon = config.icon

  return (
    <div
      className={cn(
        "rounded-lg border-l-4 bg-card p-4",
        config.borderColor,
        className
      )}
    >
      <div className="mb-3 flex items-center gap-2">
        <div className={cn("rounded-md p-1.5", config.bgColor)}>
          <Icon className={cn("h-4 w-4", config.textColor)} />
        </div>
        <span className={cn("text-sm font-medium", config.textColor)}>
          {config.name}
        </span>
      </div>
      <div className="text-sm text-foreground">{children}</div>
    </div>
  )
}
