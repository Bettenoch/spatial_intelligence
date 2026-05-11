"""
models/route.py
─────────────────────────────────────────────────────────────────────────────
Route data model — the computed path for a driver to fulfil a cluster.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RoutingMethod(str, Enum):
    EUCLIDEAN = "euclidean"
    HAVERSINE = "haversine"
    STREET_NETWORK = "street_network"


class RouteWaypoint(BaseModel):
    lat: float
    lon: float
    order_id: Optional[str] = None   # None = depot / intermediate road point
    sequence: int = 0


class Route(BaseModel):
    id: str
    cluster_id: str
    driver_id: str
    driver_name: str = ""           # ← ADD THIS TOO
    method: RoutingMethod
    waypoints: List[RouteWaypoint] = Field(default_factory=list)
    geojson: Optional[Dict[str, Any]] = None
    total_distance_km: float = 0.0
    estimated_duration_minutes: float = 0.0
    naive_distance_km: float = 0.0
    color: str = "#00ccff"          # ← AND THIS

    model_config = {"use_enum_values": True}