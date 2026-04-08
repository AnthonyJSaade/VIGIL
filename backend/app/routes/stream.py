"""SSE stream endpoint — streams agent events for a run in real time."""

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from ..streaming.sse import bus

router = APIRouter(prefix="/api/runs", tags=["stream"])


@router.get("/{run_id}/stream")
async def stream_run_events(run_id: str) -> StreamingResponse:
    return StreamingResponse(
        bus.subscribe(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
