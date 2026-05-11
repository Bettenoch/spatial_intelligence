"""
models/simulation.py — UPDATED
─────────────────────────────────────────────────────────────────────────────
Changes:
  - SimulationConfig: added restaurant_count field
  - SimulationState:  added restaurants dict
  - DeliveryRecord:   new model for the post-simulation table
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
from app.models.restaurant import Restaurant
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
    order_count: int = Field(default=30, ge=5, le=9999)
    driver_count: int = Field(default=5, ge=1, le=9999)
    restaurant_count: int = Field(default=5, ge=1, le=10)   # ← NEW
    routing_method: RoutingMethod = RoutingMethod.STREET_NETWORK
    scenario_label: str = "UberEats Nairobi — Friday 7PM"
    simulation_speed: float = Field(default=8.0, ge=0.1, le=10.0)


class DeliveryRecord(BaseModel):
    """One row in the post-simulation delivery table."""
    order_id: str
    driver_name: str
    restaurant_name: str
    restaurant_zone: str
    customer_zone: str
    ordered_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    duration_minutes: Optional[float] = None
    distance_km: float = 0.0
    algorithm: str = "street_network"
    status: str = "delivered"


class SimulationState(BaseModel):
    """Full simulation snapshot."""
    session_id: str = Field(default_factory=lambda: f"sim_{uuid4().hex[:10]}")
    config: SimulationConfig = Field(default_factory=SimulationConfig)
    status: SimulationStatus = SimulationStatus.INITIALISING
    orders: Dict[str, Order] = Field(default_factory=dict)
    drivers: Dict[str, Driver] = Field(default_factory=dict)
    restaurants: Dict[str, Restaurant] = Field(default_factory=dict)   # ← NEW
    clusters: Dict[str, Cluster] = Field(default_factory=dict)
    routes: Dict[str, Route] = Field(default_factory=dict)
    delivery_records: List[DeliveryRecord] = Field(default_factory=list)  # ← NEW
    metrics: SimulationMetrics = Field(default_factory=SimulationMetrics)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = {"use_enum_values": True}