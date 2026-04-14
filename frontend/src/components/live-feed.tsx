// LiveFeed — real-time agent activity log powered by Server-Sent Events.
//
// Opens an EventSource connection to GET /api/runs/{id}/stream and appends
// each incoming event to a scrolling list. Role labels are color-coded to
// match the backend agent personas: hunter=teal, surgeon=amber, critic=purple,
// verifier=green.
//
// completeCalled is a ref rather than state so that the onRunComplete callback
// fires exactly once even if the SSE stream closes and the onerror handler also
// fires in the same tick.
"use client";

import { useEffect, useRef, useState } from "react";

const API_BASE = "http://localhost:8000";

interface AgentEvent {
  id: string;
  role: string;
  action: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

const ROLE_COLORS: Record<string, string> = {
  hunter: "text-teal-400",
  surgeon: "text-amber-400",
  critic: "text-purple-400",
  verifier: "text-green-400",
};

function formatAction(action: string): string {
  return action.replace(/_/g, " ");
}

export default function LiveFeed({
  runId,
  onRunComplete,
}: {
  runId: string;
  onRunComplete?: () => void;
}) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const completeCalled = useRef(false);

  useEffect(() => {
    const source = new EventSource(`${API_BASE}/api/runs/${runId}/stream`);

    source.onopen = () => setConnected(true);

    source.onmessage = (e) => {
      try {
        const evt: AgentEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, evt]);

        if (
          evt.action === "scan_completed" &&
          onRunComplete &&
          !completeCalled.current
        ) {
          completeCalled.current = true;
          onRunComplete();
        }
      } catch {
        /* ignore malformed events */
      }
    };

    source.onerror = () => {
      setConnected(false);
      source.close();
      if (onRunComplete && !completeCalled.current) {
        completeCalled.current = true;
        onRunComplete();
      }
    };

    return () => source.close();
  }, [runId, onRunComplete]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Agent Activity</h3>
        <span
          className={`inline-flex items-center gap-1.5 text-xs ${
            connected ? "text-green-400" : "text-zinc-500"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              connected ? "bg-green-400 animate-pulse" : "bg-zinc-600"
            }`}
          />
          {connected ? "Live" : "Disconnected"}
        </span>
      </div>
      <div className="max-h-80 overflow-y-auto font-mono text-xs leading-relaxed">
        {events.length === 0 && (
          <p className="text-zinc-600">Waiting for events...</p>
        )}
        {events.map((evt) => (
          <div key={evt.id} className="flex gap-2 py-0.5">
            <span className="shrink-0 text-zinc-600">
              {new Date(evt.timestamp).toLocaleTimeString()}
            </span>
            <span
              className={`shrink-0 font-semibold uppercase ${
                ROLE_COLORS[evt.role] ?? "text-zinc-400"
              }`}
            >
              {evt.role}
            </span>
            <span className="text-zinc-300">{formatAction(evt.action)}</span>
            {evt.payload && Object.keys(evt.payload).length > 0 && (
              <span className="truncate text-zinc-600">
                {JSON.stringify(evt.payload)}
              </span>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
