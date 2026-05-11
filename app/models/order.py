"""
models/order.py  — UPDATED
─────────────────────────────────────────────────────────────────────────────
Order data model — represents a single delivery request.

Changes:
  - Added restaurant_id: which restaurant the order comes from
  - Added restaurant_name: denormalized for display
  - Added ordered_at: when the order was placed
  - Added delivered_at: when delivery was confirmed
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

    # Delivery destination (customer)
    lat: float = Field(..., description="Customer delivery latitude (WGS84)")
    lon: float = Field(..., description="Customer delivery longitude (WGS84)")
    zone: str = Field(..., description="Customer neighbourhood name")

    # Source (restaurant)
    restaurant_id: Optional[str] = None
    restaurant_name: str = ""
    restaurant_lat: Optional[float] = None
    restaurant_lon: Optional[float] = None
    restaurant_zone: str = ""
    restaurant_road_node_id: Optional[int] = None

    order_type: OrderType = OrderType.FOOD
    status: OrderStatus = OrderStatus.PENDING
    cluster_id: Optional[str] = None
    driver_id: Optional[str] = None

    # Timestamps
    ordered_at: datetime = Field(default_factory=datetime.utcnow)
    pickup_at: Optional[datetime] = None     # when driver picks up from restaurant
    delivered_at: Optional[datetime] = None  # when delivered to customer

    estimated_prep_minutes: int = Field(default=15, ge=5, le=45)

    # Node id on the road graph (customer destination)
    road_node_id: Optional[int] = None

    model_config = {"use_enum_values": True}