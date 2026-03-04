"""Server-Sent Events — real-time state push for dashboards and integrations."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.constants import SSE_KEEPALIVE_INTERVAL

logger = logging.getLogger(__name__)

router = APIRouter()

# Connected SSE clients
_clients: list[asyncio.Queue] = []


def broadcast(event: str, data: dict):
    """Push an event to all connected SSE clients."""
    payload = {
        "event": event,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    for queue in _clients:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # Client too slow, skip


@router.get("/events")
async def event_stream(request: Request):
    """SSE stream — subscribe for real-time VPN state changes.

    Events: vpn_state, vpn_status_update, port_forward, reconnect, health
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _clients.append(queue)

    async def generate():
        try:
            # Send initial keepalive
            yield f": connected\n\n"

            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_INTERVAL)
                    yield f"event: {payload['event']}\ndata: {json.dumps(payload['data'])}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive to prevent connection drop
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _clients.remove(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
