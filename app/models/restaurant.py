"""
models/restaurant.py
─────────────────────────────────────────────────────────────────────────────
Restaurant data model — represents a food source location.
Orders originate FROM restaurants and are delivered TO customers.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


RESTAURANT_NAMES = [
    "Java House",
    "KFC Nairobi",
    "Mama's Kitchen",
    "Artcaffe",
    "Pizza Inn",
    "Galito's",
    "Steers",
    "Chicken Inn",
    "Burger Dome",
    "Ranalo Foods",
    "Wangari's Kitchen",
    "Big Square",
    "Nyama Choma Ranch",
    "The Brew Bistro",
    "Carnivore Restaurant",
]

CUISINE_TYPES = [
    "Kenyan", "Fast Food", "Pizza", "Burgers", "Chicken",
    "Indian", "Chinese", "Italian", "Breakfast", "Grill",
]


class Restaurant(BaseModel):
    id: str = Field(default_factory=lambda: f"rst_{uuid4().hex[:6]}")
    name: str
    lat: float
    lon: float
    zone: str
    cuisine_type: str = "Kenyan"
    road_node_id: Optional[int] = None

    model_config = {"use_enum_values": True}