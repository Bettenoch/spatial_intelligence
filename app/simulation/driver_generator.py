"""
simulation/driver_generator.py
─────────────────────────────────────────────────────────────────────────────
Generates fake Uber Eats riders with realistic Nairobi starting positions.
Drivers spawn near commercial hubs (restaurants, shops) — not in suburbs.

FIX: Name deduplication — when count > len(DRIVER_NAMES), the old code
appended "Driver N" suffixes. But random.sample with count=5 and 10 names
was fine. The "#2" suffix visible in the UI came from the simulation_service
calling generate_drivers twice (once in scenario_builder, once in the VRP
setup), producing two sets of names that collide. We now:

  1. Never use random.sample — instead use a deterministic shuffle so names
     are consistent and don't collide if called twice with the same count.
  2. Return a stable list: the Nth call with count=5 always returns the same
     5 names (seeded by driver index, not random) so double-calls are
     idempotent.
  3. The fallback for count > 10 appends the zone name, not "#N", so if
     you ever run 11+ drivers the legend reads "Brian K. (Rongai)" not
     "Driver 11".
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import random
from typing import List

import numpy as np

from app.models.driver import Driver
from app.simulation.order_generator import NAIROBI_HOTSPOTS
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

# All available names — 10 unique entries.
# These are used in index order (not random.sample) so the first `count`
# names are always the same for a given count, making double-calls safe.
_ALL_DRIVER_NAMES = [
    "Brian K.",
    "Wanjiru M.",
    "Otieno D.",
    "Aisha N.",
    "Kamau J.",
    "Njeri W.",
    "Omondi P.",
    "Fatuma A.",
    "Mwangi T.",
    "Kerubo S.",
]

# Keep the old export name so order_generator.py import still works
DRIVER_NAMES = _ALL_DRIVER_NAMES


def _unique_driver_names(count: int) -> List[str]:
    """
    Return `count` unique driver names.

    For count ≤ 10: return the first `count` entries from _ALL_DRIVER_NAMES
    (deterministic — no randomness — so a double-call returns the same names).

    For count > 10: cycle through the list and append the depot zone name
    to disambiguate (e.g. "Brian K. (Rongai)") instead of "Driver N".
    """
    if count <= len(_ALL_DRIVER_NAMES):
        # Deterministic slice — always the same names for the same count.
        # Using a fixed seed shuffle lets us vary ordering without randomness
        # bleeding across calls.
        rng = random.Random(42)
        shuffled = _ALL_DRIVER_NAMES[:]
        rng.shuffle(shuffled)
        return shuffled[:count]

    # More drivers than base names — extend with zone suffixes
    names: List[str] = []
    for i in range(count):
        base = _ALL_DRIVER_NAMES[i % len(_ALL_DRIVER_NAMES)]
        zone = DRIVER_ZONES[i % len(DRIVER_ZONES)][2]
        if i < len(_ALL_DRIVER_NAMES):
            names.append(base)
        else:
            # Suffix with zone to disambiguate (never "#N")
            names.append(f"{base} ({zone})")
    return names


def generate_drivers(count: int, snap_to_graph: bool = True) -> List[Driver]:
    """
    Generate `count` drivers positioned across Nairobi depot zones.

    Args:
        count:          Number of drivers to spawn (1–8)
        snap_to_graph:  If True, snaps starting position to road network.

    Returns:
        List of Driver objects with unique names.
    """
    drivers: List[Driver] = []
    names = _unique_driver_names(count)

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