"""
models/order.py
─────────────────────────────────────────────────────────────────────────────
Order data model — represents a single delivery request.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    PENDING = "pending"
    CLUSTERED = "clustered"
    ASSIGNED = "assigned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"


class OrderType(str, Enum):
    FOOD = "food"
    GROCERY = "grocery"
    PHARMACY = "pharmacy"
    ELECTRONICS = "electronics"


class Order(BaseModel):
    id: str = Field(default_factory=lambda: f"ord_{uuid4().hex[:8]}")
    lat: float = Field(..., description="Delivery latitude (WGS84)")
    lon: float = Field(..., description="Delivery longitude (WGS84)")
    zone: str = Field(..., description="Nairobi neighbourhood name")
    order_type: OrderType = OrderType.FOOD
    status: OrderStatus = OrderStatus.PENDING
    cluster_id: Optional[str] = None
    driver_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    delivered_at: Optional[datetime] = None
    estimated_prep_minutes: int = Field(default=15, ge=5, le=45)
    # Node id on the road graph (set after snapping)
    road_node_id: Optional[int] = None

    model_config = {"use_enum_values": True}