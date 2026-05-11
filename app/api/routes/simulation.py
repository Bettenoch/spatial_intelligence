"""
app/api/routes/simulation.py — UPDATED
─────────────────────────────────────────────────────────────────────────────
Changes:
  - Validates restaurant_count (1–10)
  - GET /simulation/{id} returns delivery_records for the table
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.core.config import settings
from app.core.graph_loader import graph_loader
from app.models.simulation import SimulationConfig, SimulationState
from app.simulation.scenario_builder import build_scenario
from app.services.simulation_service import run_simulation

router = APIRouter(prefix="/api", tags=["simulation"])

_simulations: dict[str, SimulationState] = {}


@router.post("/simulate", status_code=status.HTTP_202_ACCEPTED)
async def start_simulation(
    config: SimulationConfig,
    background_tasks: BackgroundTasks,
):
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
    # Validate restaurant count (hardcoded max 10)
    if config.restaurant_count < 1 or config.restaurant_count > 10:
        raise HTTPException(
            status_code=400,
            detail="restaurant_count must be between 1 and 10",
        )

    if not graph_loader.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Road graph is still loading. Please retry in a few seconds.",
        )

    state = build_scenario(config)
    _simulations[state.session_id] = state

    background_tasks.add_task(_run_and_store, state)

    return {
        "session_id": state.session_id,
        "ws_url": f"/ws/simulation/{state.session_id}",
        "order_count": len(state.orders),
        "driver_count": len(state.drivers),
        "restaurant_count": len(state.restaurants),
        "routing_method": config.routing_method,
        "message": f"Simulation started. Connect to WebSocket at /ws/simulation/{state.session_id}",
    }


@router.get("/scenario")
async def get_default_scenario():
    return SimulationConfig().model_dump()


@router.get("/simulation/{session_id}")
async def get_simulation_state(session_id: str):
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
        "restaurant_count": len(state.restaurants),
        "metrics": state.metrics.model_dump(),
        "delivery_records": [r.model_dump() for r in state.delivery_records],
        "started_at": state.started_at.isoformat(),
        "completed_at": state.completed_at.isoformat() if state.completed_at else None,
    }


@router.get("/health")
async def health_check():
    from app.websocket.manager import ws_manager
    return {
        "status": "ok",
        "graph": graph_loader.stats(),
        "active_simulations": len(_simulations),
        "websocket_connections": ws_manager.total_connections(),
    }


async def _run_and_store(state: SimulationState) -> None:
    final_state = await run_simulation(state)
    _simulations[state.session_id] = final_state