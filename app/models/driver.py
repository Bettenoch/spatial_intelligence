"""
models/driver.py
─────────────────────────────────────────────────────────────────────────────
Driver data model — represents a delivery rider.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class DriverStatus(str, Enum):
    IDLE = "idle"
    ASSIGNED = "assigned"
    EN_ROUTE = "en_route"
    COMPLETED = "completed"


class Driver(BaseModel):
    id: str = Field(default_factory=lambda: f"drv_{uuid4().hex[:6]}")
    name: str = Field(..., description="Display name e.g. 'Brian K.'")
    lat: float = Field(..., description="Current latitude")
    lon: float = Field(..., description="Current longitude")
    zone: str = Field(..., description="Home zone / depot zone")
    status: DriverStatus = DriverStatus.IDLE
    capacity: int = Field(default=6, description="Max orders per run")
    assigned_orders: List[str] = Field(default_factory=list)
    cluster_id: Optional[str] = None
    road_node_id: Optional[int] = None
    # Cumulative stats for this simulation
    total_distance_km: float = 0.0
    deliveries_completed: int = 0

    model_config = {"use_enum_values": True}