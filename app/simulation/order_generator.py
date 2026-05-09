"""
simulation/order_generator.py
─────────────────────────────────────────────────────────────────────────────
Generates realistic fake delivery orders across Nairobi.

Uses weighted hotspot zones so orders cluster in real commercial areas
(CBD, Westlands, Kilimani) not in forests or highways.

Each order is snapped to the nearest road node so all downstream
routing operates on valid graph nodes.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import random
from typing import Dict, List, Tuple

import numpy as np
from loguru import logger

from app.models.order import Order, OrderType
from app.core.graph_loader import graph_loader

# ── Hotspot definitions ───────────────────────────────────────────────────────
# (lat, lon, radius_km, weight, zone_name)
# Weight is proportional — higher = more orders generated here.

NAIROBI_HOTSPOTS: List[Tuple[float, float, float, float, str]] = [
    # lat         lon        radius_km  weight   zone
    (-1.2864,   36.8172,    0.8,        9.0,   "CBD"),
    (-1.2676,   36.8037,    0.6,        7.0,   "Westlands"),
    (-1.2921,   36.7826,    0.5,        6.0,   "Lavington"),
    (-1.3031,   36.7877,    0.6,        6.0,   "Kilimani"),
    (-1.2741,   36.8176,    0.5,        5.0,   "Parklands"),
    (-1.3193,   36.8091,    0.5,        5.0,   "Hurlingham"),
    (-1.2996,   36.7500,    0.7,        4.0,   "Karen"),
    (-1.2633,   36.8898,    0.5,        5.0,   "Eastleigh"),
    (-1.3060,   36.8570,    0.5,        5.0,   "South C"),
    (-1.3500,   36.6900,    0.6,        3.0,   "Rongai"),
    (-1.2195,   36.8876,    0.5,        4.0,   "Kasarani"),
    (-1.2380,   36.8673,    0.4,        4.0,   "Roysambu"),
    (-1.2740,   36.8590,    0.4,        4.0,   "Pangani"),
    (-1.3208,   36.8309,    0.4,        4.0,   "Lang'ata"),
    (-1.2939,   36.8226,    0.3,        5.0,   "Upper Hill"),
    (-1.2870,   36.8237,    0.3,        4.0,   "Milimani"),
    (-1.2601,   36.8034,    0.4,        3.0,   "Muthaiga"),
    (-1.3640,   36.6790,    0.5,        2.0,   "Ongata Rongai"),
    (-1.3041,   36.8823,    0.5,        3.0,   "Buruburu"),
    (-1.2443,   36.8955,    0.5,        3.0,   "Githurai"),
]

# Pre-compute cumulative weights for fast sampling
_WEIGHTS = [h[3] for h in NAIROBI_HOTSPOTS]
_WEIGHT_TOTAL = sum(_WEIGHTS)
_NORMALIZED_WEIGHTS = [w / _WEIGHT_TOTAL for w in _WEIGHTS]

ORDER_TYPE_WEIGHTS = {
    OrderType.FOOD:        0.55,
    OrderType.GROCERY:     0.25,
    OrderType.PHARMACY:    0.12,
    OrderType.ELECTRONICS: 0.08,
}

DRIVER_NAMES = [
    "Brian K.", "Wanjiru M.", "Otieno D.", "Aisha N.", "Kamau J.",
    "Njeri W.", "Omondi P.", "Fatuma A.", "Mwangi T.", "Kerubo S.",
]


def _sample_hotspot() -> Tuple[float, float, str]:
    """Sample a GPS point from a weighted hotspot zone."""
    idx = np.random.choice(len(NAIROBI_HOTSPOTS), p=_NORMALIZED_WEIGHTS)
    lat_c, lon_c, radius_km, _, zone = NAIROBI_HOTSPOTS[idx]

    # Gaussian noise — 1 degree ≈ 111 km
    lat_std = radius_km / 111.0
    lon_std = radius_km / (111.0 * abs(np.cos(np.radians(lat_c))))

    lat = float(np.random.normal(lat_c, lat_std))
    lon = float(np.random.normal(lon_c, lon_std))

    return lat, lon, zone


def _sample_order_type() -> OrderType:
    types = list(ORDER_TYPE_WEIGHTS.keys())
    weights = list(ORDER_TYPE_WEIGHTS.values())
    return random.choices(types, weights=weights, k=1)[0]


def generate_orders(
    count: int,
    snap_to_graph: bool = True,
) -> List[Order]:
    """
    Generate `count` fake delivery orders distributed across Nairobi.

    Args:
        count: Number of orders to generate (5–60)
        snap_to_graph: If True, snaps each coordinate to the nearest
                       road node in the loaded graph.

    Returns:
        List of Order objects ready for clustering.
    """
   

    orders: List[Order] = []
    snap_failures = 0

    for i in range(count):
        lat, lon, zone = _sample_hotspot()
        order_type = _sample_order_type()
        prep_minutes = random.randint(10, 35)

        road_node_id: int | None = None

        if snap_to_graph and graph_loader.is_ready():
            try:
                node_id, dist = graph_loader.nearest_node(lat, lon)
                G = graph_loader.get_graph()
                node_data = G.nodes[node_id]
                # Use the road-snapped coordinates
                lat = float(node_data["y"])
                lon = float(node_data["x"])
                road_node_id = node_id
            except Exception as exc:
                snap_failures += 1
                logger.debug(f"  Snap failed for order {i}: {exc}")

        order = Order(
            lat=round(lat, 6),
            lon=round(lon, 6),
            zone=zone,
            order_type=order_type,
            estimated_prep_minutes=prep_minutes,
            road_node_id=road_node_id,
        )
        orders.append(order)

    if snap_failures:
        logger.warning(f"  {snap_failures}/{count} orders used unsnapped coordinates")

    logger.info(f"📦 Generated {len(orders)} orders across {len(set(o.zone for o in orders))} zones")
    return orders


def orders_to_coordinate_array(orders: List[Order]) -> np.ndarray:
    """Return Nx2 array of [lat, lon] for use in clustering algorithms."""
    return np.array([[o.lat, o.lon] for o in orders])