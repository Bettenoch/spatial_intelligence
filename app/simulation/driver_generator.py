"""
simulation/driver_generator.py
─────────────────────────────────────────────────────────────────────────────
Generates fake Uber Eats riders with realistic Nairobi starting positions.
Drivers spawn near commercial hubs (restaurants, shops) — not in suburbs.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import random
from typing import List

import numpy as np

from app.models.driver import Driver
from app.simulation.order_generator import DRIVER_NAMES, NAIROBI_HOTSPOTS
from app.core.graph_loader import graph_loader

# Driver depot zones — where riders start their shifts
DRIVER_ZONES = [
    (-1.2864, 36.8172, "CBD"),
    (-1.2676, 36.8037, "Westlands"),
    (-1.3031, 36.7877, "Kilimani"),
    (-1.2741, 36.8176, "Parklands"),
    (-1.2996, 36.7500, "Karen"),
    (-1.3060, 36.8570, "South C"),
    (-1.2195, 36.8876, "Kasarani"),
    (-1.2939, 36.8226, "Upper Hill"),
]


def generate_drivers(count: int, snap_to_graph: bool = True) -> List[Driver]:
    """
    Generate `count` drivers positioned across Nairobi depot zones.

    Args:
        count:          Number of drivers to spawn (1–8)
        snap_to_graph:  If True, snaps starting position to road network.

    Returns:
        List of Driver objects.
    """
   

    drivers: List[Driver] = []
    names = random.sample(DRIVER_NAMES, min(count, len(DRIVER_NAMES)))
    if count > len(names):
        # If more drivers than names, add suffixed names
        extras = [f"Driver {i+1}" for i in range(count - len(names))]
        names.extend(extras)

    for i in range(count):
        # Pick a depot zone — spread drivers across city
        depot_idx = i % len(DRIVER_ZONES)
        depot_lat, depot_lon, zone = DRIVER_ZONES[depot_idx]

        # Small jitter so drivers don't all stack exactly on the same point
        jitter = 0.003   # ~330m
        lat = depot_lat + np.random.uniform(-jitter, jitter)
        lon = depot_lon + np.random.uniform(-jitter, jitter)

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
                pass  # Use unsnapped position — non-fatal

        driver = Driver(
            name=names[i],
            lat=round(lat, 6),
            lon=round(lon, 6),
            zone=zone,
            capacity=random.choice([4, 5, 6]),
            road_node_id=road_node_id,
        )
        drivers.append(driver)

    return drivers