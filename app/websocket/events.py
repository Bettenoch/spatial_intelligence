"""
websocket/events.py
─────────────────────────────────────────────────────────────────────────────
Defines every event type streamed from the backend to connected frontends.

Changes:
  - OrderCreatedEvent.Data: added `restaurant_name` field for hover tooltips
  - RouteComputedEvent.Data: added `driver_name` field for legend display
  - DriverMovedEvent.Data:   added `driver_name` field for hover tooltips
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    """Root event envelope. All events extend this."""
    event: str
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_json(self) -> str:
        return self.model_dump_json()


# ── Order events ─────────────────────────────────────────────────────────────

class OrderCreatedEvent(BaseEvent):
    event: str = "ORDER_CREATED"

    class Data(BaseModel):
        order_id: str
        lat: float
        lon: float
        zone: str
        order_type: str
        estimated_prep_minutes: int
        restaurant_name: str = ""   # ← NEW: shown on hover

    data: Data


class OrderStatusChangedEvent(BaseEvent):
    event: str = "ORDER_STATUS_CHANGED"

    class Data(BaseModel):
        order_id: str
        status: str
        driver_id: Optional[str] = None

    data: Data


# ── Cluster events ────────────────────────────────────────────────────────────

class ClusterFormedEvent(BaseEvent):
    event: str = "CLUSTER_FORMED"

    class Data(BaseModel):
        cluster_id: str
        order_ids: List[str]
        centroid_lat: float
        centroid_lon: float
        color: str
        zone_label: str
        size: int

    data: Data


# ── Route events ─────────────────────────────────────────────────────────────

class RouteComputedEvent(BaseEvent):
    event: str = "ROUTE_COMPUTED"

    class Data(BaseModel):
        route_id: str
        cluster_id: str
        driver_id: str
        driver_name: str = ""    # ← NEW: shown in legend
        method: str
        geojson: Dict[str, Any]
        total_distance_km: float
        estimated_duration_minutes: float
        naive_distance_km: float
        color: str

    data: Data


# ── Driver events ─────────────────────────────────────────────────────────────

class DriverAssignedEvent(BaseEvent):
    event: str = "DRIVER_ASSIGNED"

    class Data(BaseModel):
        driver_id: str
        driver_name: str
        cluster_id: str
        order_count: int

    data: Data


class DriverMovedEvent(BaseEvent):
    event: str = "DRIVER_MOVED"

    class Data(BaseModel):
        driver_id: str
        driver_name: str = ""    # ← NEW: shown on hover
        lat: float
        lon: float
        progress_pct: float
        current_order_id: Optional[str] = None

    data: Data


class DeliveryCompletedEvent(BaseEvent):
    event: str = "DELIVERY_COMPLETED"

    class Data(BaseModel):
        order_id: str
        driver_id: str
        time_taken_minutes: float

    data: Data


# ── Metrics events ────────────────────────────────────────────────────────────

class MetricsUpdatedEvent(BaseEvent):
    event: str = "METRICS_UPDATED"

    class Data(BaseModel):
        deliveries_completed: int
        deliveries_total: int
        optimised_distance_km: float
        naive_distance_km: float
        distance_saved_km: float
        savings_percentage: float
        fuel_saved_litres: float
        cost_saved_kes: float
        time_saved_minutes: float
        co2_saved_kg: float
        active_drivers: int
        clusters_formed: int

    data: Data


# ── System events ─────────────────────────────────────────────────────────────

class SimulationStartedEvent(BaseEvent):
    event: str = "SIMULATION_STARTED"

    class Data(BaseModel):
        session_id: str
        order_count: int
        driver_count: int
        routing_method: str
        scenario_label: str

    data: Data


class SimulationStatusEvent(BaseEvent):
    event: str = "SIMULATION_STATUS"

    class Data(BaseModel):
        status: str
        message: str

    data: Data


class SimulationCompletedEvent(BaseEvent):
    event: str = "SIMULATION_COMPLETED"

    class Data(BaseModel):
        session_id: str
        total_deliveries: int
        total_distance_km: float
        total_savings_pct: float
        duration_seconds: float

    data: Data


class ErrorEvent(BaseEvent):
    event: str = "ERROR"

    class Data(BaseModel):
        error_code: str
        message: str

    data: Data