"""SSE event bus — publish/subscribe pattern keyed by run_id.

Every agent module calls ``bus.publish()`` at key steps.  The SSE route
yields events from ``bus.subscribe()`` as a StreamingResponse.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from ..db import insert_trace_event
from ..models.trace import AgentRole, TraceAction, TraceEvent


class EventBus:
    """In-memory event bus backed by one :class:`asyncio.Queue` per run."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}

    def _get_queues(self, run_id: str) -> list[asyncio.Queue]:
        return self._queues.setdefault(run_id, [])

    async def publish(
        self,
        run_id: str,
        role: AgentRole,
        action: TraceAction,
        payload: dict | None = None,
    ) -> TraceEvent:
        """Publish an event to all subscribers for *run_id* and persist it as a
        :class:`TraceEvent`.  Returns the created event."""
        payload = payload or {}

        event = TraceEvent(
            id=str(uuid.uuid4()),
            run_id=run_id,
            role=role,
            action=action,
            payload=payload,
        )
        await insert_trace_event(event)

        sse_data = json.dumps({
            "id": event.id,
            "role": event.role.value,
            "action": event.action.value,
            "payload": event.payload,
            "timestamp": event.timestamp.isoformat(),
        })

        for queue in self._get_queues(run_id):
            await queue.put(f"event: {event.action.value}\ndata: {sse_data}\n\n")

        return event

    async def subscribe(self, run_id: str) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted strings as events arrive for *run_id*.

        The generator runs until the client disconnects or the queue is
        explicitly closed by sending ``None``.
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._get_queues(run_id).append(queue)
        try:
            while True:
                msg = await queue.get()
                if msg is None:
                    break
                yield msg
        finally:
            self._get_queues(run_id).remove(queue)
            if not self._get_queues(run_id):
                del self._queues[run_id]

    def close(self, run_id: str) -> None:
        """Signal all subscribers for *run_id* to stop."""
        for queue in self._get_queues(run_id):
            queue.put_nowait(None)


bus = EventBus()
