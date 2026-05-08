"""
models/simulation.py
─────────────────────────────────────────────────────────────────────────────
Simulation state model — the authoritative snapshot of a running simulation.
Serialised to Redis so multiple WebSocket connections share the same state.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.cluster import Cluster
from app.models.driver import Driver
from app.models.order import Order
from app.models.route import Route, RoutingMethod


class SimulationStatus(str, Enum):
    INITIALISING = "initialising"
    GENERATING_ORDERS = "generating_orders"
    CLUSTERING = "clustering"
    ROUTING = "routing"
    ANIMATING = "animating"
    COMPLETED = "completed"
    FAILED = "failed"


class SimulationMetrics(BaseModel):
    """Live-updating metrics panel data."""
    deliveries_completed: int = 0
    deliveries_total: int = 0
    optimised_distance_km: float = 0.0
    naive_distance_km: float = 0.0
    distance_saved_km: float = 0.0
    fuel_saved_litres: float = 0.0
    cost_saved_kes: float = 0.0
    time_saved_minutes: float = 0.0
    co2_saved_kg: float = 0.0
    active_drivers: int = 0
    clusters_formed: int = 0

    @property
    def savings_percentage(self) -> float:
        if self.naive_distance_km == 0:
            return 0.0
        return round((self.distance_saved_km / self.naive_distance_km) * 100, 1)


class SimulationConfig(BaseModel):
    """Parameters chosen by the user before the simulation starts."""
    order_count: int = Field(default=30, ge=5, le=60)
    driver_count: int = Field(default=5, ge=1, le=8)
    routing_method: RoutingMethod = RoutingMethod.STREET_NETWORK
    scenario_label: str = "UberEats Nairobi — Friday 7PM"


class SimulationState(BaseModel):
    """
    Full simulation snapshot.
    Stored in Redis under key: simulation:{session_id}
    """
    session_id: str = Field(default_factory=lambda: f"sim_{uuid4().hex[:10]}")
    config: SimulationConfig = Field(default_factory=SimulationConfig)
    status: SimulationStatus = SimulationStatus.INITIALISING
    orders: Dict[str, Order] = Field(default_factory=dict)
    drivers: Dict[str, Driver] = Field(default_factory=dict)
    clusters: Dict[str, Cluster] = Field(default_factory=dict)
    routes: Dict[str, Route] = Field(default_factory=dict)
    metrics: SimulationMetrics = Field(default_factory=SimulationMetrics)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = {"use_enum_values": True}