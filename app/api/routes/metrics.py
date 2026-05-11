"""
app/api/routes/metrics.py
─────────────────────────────────────────────────────────────────────────────
REST endpoint for fetching final simulation metrics.
Useful for clients that reconnect after a simulation completes.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics/{session_id}")
async def get_metrics(session_id: str):
    """Return final metrics for a completed simulation."""
    from app.api.routes.simulation import _simulations

    state = _simulations.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Simulation '{session_id}' not found.")

    m = state.metrics
    return {
        "session_id": session_id,
        "status": state.status,
        "metrics": m.model_dump(),
        "savings_percentage": m.savings_percentage,
        "summary": {
            "deliveries": f"{m.deliveries_completed}/{m.deliveries_total}",
            "distance_saved": f"{m.distance_saved_km:.1f} km",
            "fuel_saved": f"{m.fuel_saved_litres:.1f} L",
            "cost_saved": f"KES {m.cost_saved_kes:,.0f}",
            "co2_saved": f"{m.co2_saved_kg:.2f} kg",
            "time_saved": f"{m.time_saved_minutes:.0f} min",
        },
    }