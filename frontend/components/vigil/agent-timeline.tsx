"use client"

import { cn } from "@/lib/utils"
import { agentConfigs, type AgentType } from "./agent-card"

export interface TimelineEvent {
  id: string
  agent: AgentType
  action: string
  timestamp: string
  details?: string
}

interface AgentTimelineProps {
  events: TimelineEvent[]
  className?: string
  actionSlot?: React.ReactNode
}

export function AgentTimeline({ events, className, actionSlot }: AgentTimelineProps) {
  return (
    <div className={cn("relative", className)}>
      {/* Vertical line */}
      <div className="absolute left-[9px] top-0 bottom-0 w-px bg-border" />
      
      <div className="space-y-2.5">
        {events.map((event, index) => {
          const config = agentConfigs[event.agent]
          const Icon = config.icon
          const isLatest = index === events.length - 1 && !actionSlot

          return (
            <div key={event.id} className="relative flex gap-3 pl-7">
              {/* Dot */}
              <div
                className={cn(
                  "absolute left-0 top-0.5 z-10 h-[18px] w-[18px] rounded-full border-2 flex items-center justify-center",
                  isLatest ? "border-current" : "border-border bg-card"
                )}
                style={{ 
                  borderColor: isLatest ? config.color : undefined,
                  backgroundColor: isLatest ? `${config.color}20` : undefined
                }}
              >
                <Icon 
                  className="h-2.5 w-2.5" 
                  style={{ color: config.color }}
                />
              </div>

              {/* Content */}
              <div className="flex-1 pb-1">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span 
                      className="text-xs font-medium"
                      style={{ color: config.color }}
                    >
                      {config.name}
                    </span>
                    <p className="text-xs text-foreground leading-snug">{event.action}</p>
                    {event.details && (
                      <p className="mt-0.5 text-[10px] text-muted-foreground leading-snug">
                        {event.details}
                      </p>
                    )}
                  </div>
                  <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                    {event.timestamp}
                  </span>
                </div>
              </div>
            </div>
          )
        })}

        {/* Action slot - renders below the last event */}
        {actionSlot && (
          <div className="relative flex gap-3 pl-7">
            {/* Dot placeholder */}
            <div className="absolute left-0 top-0.5 z-10 h-[18px] w-[18px] rounded-full border-2 border-dashed border-muted-foreground/30 flex items-center justify-center bg-card" />
            
            {/* Action content */}
            <div className="flex-1 pt-0.5">
              {actionSlot}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
