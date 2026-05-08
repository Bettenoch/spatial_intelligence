"""
websocket/manager.py
─────────────────────────────────────────────────────────────────────────────
Manages all active WebSocket connections.

Architecture:
  - One manager instance lives for the life of the app (module-level singleton)
  - Connections are keyed by session_id
  - Multiple clients can connect to the same session (e.g. mobile + desktop)
  - Broadcast sends an event to all clients watching a session
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import DefaultDict, List, Set

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from app.websocket.events import BaseEvent, ErrorEvent


class ConnectionManager:
    """
    Tracks active WebSocket connections grouped by session_id.
    Thread-safe enough for a single-process async server.
    """

    def __init__(self) -> None:
        # session_id → set of connected WebSocket objects
        self._connections: DefaultDict[str, Set[WebSocket]] = defaultdict(set)

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections[session_id].add(websocket)
        count = len(self._connections[session_id])
        logger.info(f"🔌 WS connect: session={session_id} | total={count}")

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """Remove a WebSocket from the tracking set."""
        self._connections[session_id].discard(websocket)
        count = len(self._connections[session_id])
        logger.info(f"🔌 WS disconnect: session={session_id} | remaining={count}")
        # Clean up empty session buckets
        if count == 0:
            del self._connections[session_id]

    # ── Sending ───────────────────────────────────────────────────────────────

    async def broadcast(self, session_id: str, event: BaseEvent) -> None:
        """
        Send an event to all clients watching this session.
        Disconnected clients are silently removed.
        """
        connections = list(self._connections.get(session_id, set()))
        if not connections:
            return

        payload = event.to_json()
        dead: List[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._connections[session_id].discard(ws)
            logger.debug(f"  Removed dead connection from session {session_id}")

    async def send_personal(self, websocket: WebSocket, event: BaseEvent) -> None:
        """Send an event to a single connection only."""
        try:
            await websocket.send_text(event.to_json())
        except Exception as exc:
            logger.warning(f"  Personal send failed: {exc}")

    # ── Utilities ─────────────────────────────────────────────────────────────

    def active_sessions(self) -> List[str]:
        return list(self._connections.keys())

    def connection_count(self, session_id: str) -> int:
        return len(self._connections.get(session_id, set()))

    def total_connections(self) -> int:
        return sum(len(v) for v in self._connections.values())


# ── Module-level singleton ─────────────────────────────────────────────────────

ws_manager = ConnectionManager()