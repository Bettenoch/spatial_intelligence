"""
app/api/routes/simulation.py
─────────────────────────────────────────────────────────────────────────────
REST endpoints for simulation management.

POST /simulate        → Start a new simulation, returns session_id
GET  /scenario        → Get default scenario config
GET  /simulation/{id} → Get current state of a simulation
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.core.config import settings
from app.core.exceptions import SimulationLimitExceededError
from app.core.graph_loader import graph_loader
from app.models.simulation import SimulationConfig, SimulationState
from app.simulation.scenario_builder import build_scenario
from app.services.simulation_service import run_simulation

router = APIRouter(prefix="/api", tags=["simulation"])

# In-memory simulation store (prod: move to Redis)
_simulations: dict[str, SimulationState] = {}


@router.post("/simulate", status_code=status.HTTP_202_ACCEPTED)
async def start_simulation(
    config: SimulationConfig,
    background_tasks: BackgroundTasks,
):
    """
    Start a new delivery simulation.

    The simulation runs asynchronously in the background.
    Connect via WebSocket at /ws/simulation/{session_id} to receive live events.

    Returns:
        session_id to use for the WebSocket connection.
    """
    # Validate limits
    if config.order_count > settings.simulation_max_orders:
        raise HTTPException(
            status_code=400,
            detail=f"order_count exceeds maximum of {settings.simulation_max_orders}",
        )
    if config.driver_count > settings.simulation_max_drivers:
        raise HTTPException(
            status_code=400,
            detail=f"driver_count exceeds maximum of {settings.simulation_max_drivers}",
        )

    if not graph_loader.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Road graph is still loading. Please retry in a few seconds.",
        )

    # Build scenario synchronously (fast — just data generation)
    state = build_scenario(config)
    _simulations[state.session_id] = state

    # Run the actual simulation in the background
    background_tasks.add_task(_run_and_store, state)

    return {
        "session_id": state.session_id,
        "ws_url": f"/ws/simulation/{state.session_id}",
        "order_count": len(state.orders),
        "driver_count": len(state.drivers),
        "routing_method": config.routing_method,
        "message": f"Simulation started. Connect to WebSocket at /ws/simulation/{state.session_id}",
    }


@router.get("/scenario")
async def get_default_scenario():
    """Return the default simulation configuration."""
    return SimulationConfig().model_dump()


@router.get("/simulation/{session_id}")
async def get_simulation_state(session_id: str):
    """Return the current state of a simulation."""
    state = _simulations.get(session_id)
    if not state:
        raise HTTPException(
            status_code=404,
            detail=f"Simulation '{session_id}' not found.",
        )
    return {
        "session_id": state.session_id,
        "status": state.status,
        "order_count": len(state.orders),
        "cluster_count": len(state.clusters),
        "route_count": len(state.routes),
        "metrics": state.metrics.model_dump(),
        "started_at": state.started_at.isoformat(),
        "completed_at": state.completed_at.isoformat() if state.completed_at else None,
    }


@router.get("/health")
async def health_check():
    """System health — graph status, active simulations, WS connections."""
    from app.websocket.manager import ws_manager
    return {
        "status": "ok",
        "graph": graph_loader.stats(),
        "active_simulations": len(_simulations),
        "websocket_connections": ws_manager.total_connections(),
    }


async def _run_and_store(state: SimulationState) -> None:
    """Background task: run simulation and update stored state."""
    final_state = await run_simulation(state)
    _simulations[state.session_id] = final_state