"""
simulation/restaurant_generator.py
─────────────────────────────────────────────────────────────────────────────
Generates fake restaurants positioned at real Nairobi commercial hotspots.
Restaurants are the SOURCE of orders — drivers pick up from here and
deliver to customer locations.

Each restaurant is snapped to the road network so routing works correctly.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import random
from typing import List

import numpy as np
from loguru import logger

from app.models.restaurant import Restaurant, RESTAURANT_NAMES, CUISINE_TYPES
from app.core.graph_loader import graph_loader

# Restaurant anchor zones — real commercial areas in Nairobi
# (lat, lon, zone_name)
RESTAURANT_ANCHORS = [
    (-1.2864,  36.8172, "CBD"),
    (-1.2676,  36.8037, "Westlands"),
    (-1.3031,  36.7877, "Kilimani"),
    (-1.2741,  36.8176, "Parklands"),
    (-1.2996,  36.7500, "Karen"),
    (-1.3060,  36.8570, "South C"),
    (-1.2195,  36.8876, "Kasarani"),
    (-1.2939,  36.8226, "Upper Hill"),
    (-1.2633,  36.8898, "Eastleigh"),
    (-1.3193,  36.8091, "Hurlingham"),
]


def generate_restaurants(count: int, snap_to_graph: bool = True) -> List[Restaurant]:
    """
    Generate `count` restaurants distributed across Nairobi commercial zones.

    Args:
        count:          Number of restaurants (1–10)
        snap_to_graph:  If True, snaps to nearest road node

    Returns:
        List of Restaurant objects
    """
    count = min(count, len(RESTAURANT_NAMES))
    count = min(count, len(RESTAURANT_ANCHORS))

    # Pick deterministic anchors (spread across city, not random)
    rng = random.Random(99)
    anchors = RESTAURANT_ANCHORS[:count]
    rng.shuffle(anchors)

    # Shuffle name pool deterministically
    name_pool = RESTAURANT_NAMES[:]
    rng.shuffle(name_pool)
    cuisine_pool = CUISINE_TYPES[:]
    rng.shuffle(cuisine_pool)

    restaurants: List[Restaurant] = []

    for i, (anchor_lat, anchor_lon, zone) in enumerate(anchors):
        # Small jitter so restaurants aren't all dead-center
        jitter = 0.002  # ~220m
        lat = anchor_lat + np.random.uniform(-jitter, jitter)
        lon = anchor_lon + np.random.uniform(-jitter, jitter)

        road_node_id: int | None = None

        if snap_to_graph and graph_loader.is_ready():
            try:
                node_id, _ = graph_loader.nearest_node(lat, lon)
                G = graph_loader.get_graph()
                node_data = G.nodes[node_id]
                lat = float(node_data["y"])
                lon = float(node_data["x"])
                road_node_id = node_id
            except Exception:
                pass  # Use unsnapped — non-fatal

        restaurant = Restaurant(
            name=name_pool[i % len(name_pool)],
            lat=round(lat, 6),
            lon=round(lon, 6),
            zone=zone,
            cuisine_type=cuisine_pool[i % len(cuisine_pool)],
            road_node_id=road_node_id,
        )
        restaurants.append(restaurant)

    logger.info(f"🏪 Generated {len(restaurants)} restaurants across Nairobi")
    return restaurants