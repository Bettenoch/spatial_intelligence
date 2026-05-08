"""
app/api/websocket_routes.py
─────────────────────────────────────────────────────────────────────────────
WebSocket endpoint for live simulation event streaming.

Connect to: ws://{host}/ws/simulation/{session_id}

The client receives a stream of JSON events as the simulation progresses.
See websocket/events.py for the full event schema reference.

Protocol:
  1. Client connects
  2. Server sends welcome message
  3. Simulation events stream in real-time
  4. Client optionally sends { "action": "switch_method", "method": "..." }
     to change routing method mid-simulation
  5. Connection closes on SIMULATION_COMPLETED or client disconnect
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.websocket.manager import ws_manager
from app.websocket.events import SimulationStatusEvent

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/simulation/{session_id}")
async def simulation_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for a specific simulation session.

    Multiple clients can connect to the same session_id (e.g. mobile + desktop).
    All receive the same event stream.
    """
    await ws_manager.connect(websocket, session_id)

    # Send a welcome / sync message immediately on connect
    await ws_manager.send_personal(
        websocket,
        SimulationStatusEvent(
            session_id=session_id,
            data=SimulationStatusEvent.Data(
                status="connected",
                message=f"Connected to simulation {session_id}. Events will stream shortly.",
            ),
        ),
    )

    try:
        while True:
            # Keep connection alive; handle optional client messages
            try:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                action = msg.get("action")

                if action == "ping":
                    await websocket.send_text(json.dumps({"event": "PONG"}))
                elif action == "switch_method":
                    # Future: allow mid-simulation method switching
                    new_method = msg.get("method")
                    logger.info(f"Method switch requested: {new_method} (session={session_id})")
                    # TODO: signal simulation_service to use new method for subsequent clusters

            except Exception:
                break

    except WebSocketDisconnect:
        logger.info(f"WS client disconnected from session {session_id}")
    finally:
        ws_manager.disconnect(websocket, session_id)