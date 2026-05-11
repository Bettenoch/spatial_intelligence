"""
services/routing_service.py
─────────────────────────────────────────────────────────────────────────────
The routing decision layer.

Receives a cluster + routing method, dispatches to the correct algorithm,
returns a fully constructed Route object with GeoJSON geometry.

This is the Strategy pattern in practice:
  - Same interface regardless of which routing method is selected
  - Frontend switches method → this service handles the swap transparently
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np
from loguru import logger

from app.algorithms.distance.euclidean import (
    euclidean_distance_matrix,
    nearest_neighbour_tour,
    build_euclidean_geojson,
)
from app.algorithms.distance.haversine import (
    haversine_distance,
    nearest_neighbour_tour_haversine,
    build_haversine_geojson,
    total_route_distance,
)
from app.algorithms.routing.osrm_client import osrm_client
from app.core.config import settings
from app.core.exceptions import UnsupportedRoutingMethod
from app.models.cluster import Cluster
from app.models.driver import Driver
from app.models.order import Order
from app.models.route import Route, RoutingMethod, RouteWaypoint


async def compute_route(
    cluster: Cluster,
    driver: Driver,
    orders: Dict[str, Order],
    method: RoutingMethod,
) -> Route:
    """
    Compute the optimal route for a driver to fulfil all orders in a cluster.

    Args:
        cluster:  The order cluster to route
        driver:   The assigned driver (starting position)
        orders:   Full orders lookup dict
        method:   Which routing algorithm to use

    Returns:
        Route object with GeoJSON geometry, distance, and duration.
    """
    cluster_orders = [orders[oid] for oid in cluster.order_ids if oid in orders]
    if not cluster_orders:
        return _empty_route(cluster, driver, method)

    if method == RoutingMethod.EUCLIDEAN:
        return await _route_euclidean(cluster, driver, cluster_orders)
    elif method == RoutingMethod.HAVERSINE:
        return await _route_haversine(cluster, driver, cluster_orders)
    elif method == RoutingMethod.STREET_NETWORK:
        return await _route_street_network(cluster, driver, cluster_orders)
    else:
        raise UnsupportedRoutingMethod(str(method))


# ── Euclidean routing ────────────────────────────────────────────────────────

async def _route_euclidean(
    cluster: Cluster,
    driver: Driver,
    orders: List[Order],
) -> Route:
    """Straight-line Euclidean routing with nearest-neighbour TSP."""
    # Build coordinate array: [driver, order1, order2, …]
    all_coords = np.array(
        [[driver.lat, driver.lon]] + [[o.lat, o.lon] for o in orders]
    )
    tour, total_dist = nearest_neighbour_tour(all_coords, start_idx=0)
    geojson = build_euclidean_geojson(all_coords, tour)

    naive_dist = _naive_distance(driver, orders)
    duration = _estimate_duration(total_dist)

    waypoints = _build_waypoints(all_coords, tour, orders)

    return Route(
        id=f"rte_{uuid4().hex[:8]}",
        cluster_id=cluster.id,
        driver_id=driver.id,
        method=RoutingMethod.EUCLIDEAN,
        waypoints=waypoints,
        geojson=geojson,
        total_distance_km=round(total_dist, 3),
        estimated_duration_minutes=round(duration, 1),
        naive_distance_km=round(naive_dist, 3),
    )


# ── Haversine routing ────────────────────────────────────────────────────────

async def _route_haversine(
    cluster: Cluster,
    driver: Driver,
    orders: List[Order],
) -> Route:
    """Haversine distance routing with nearest-neighbour TSP."""
    all_coords = np.array(
        [[driver.lat, driver.lon]] + [[o.lat, o.lon] for o in orders]
    )
    tour, total_dist = nearest_neighbour_tour_haversine(all_coords, start_idx=0)
    geojson = build_haversine_geojson(all_coords, tour)

    naive_dist = _naive_distance(driver, orders)
    duration = _estimate_duration(total_dist)
    waypoints = _build_waypoints(all_coords, tour, orders)

    return Route(
        id=f"rte_{uuid4().hex[:8]}",
        cluster_id=cluster.id,
        driver_id=driver.id,
        method=RoutingMethod.HAVERSINE,
        waypoints=waypoints,
        geojson=geojson,
        total_distance_km=round(total_dist, 3),
        estimated_duration_minutes=round(duration, 1),
        naive_distance_km=round(naive_dist, 3),
    )


# ── Street network routing ────────────────────────────────────────────────────

async def _route_street_network(
    cluster: Cluster,
    driver: Driver,
    orders: List[Order],
) -> Route:
    """
    Real street routing via OSRM.

    Order sequence optimised by nearest-neighbour on Haversine distances
    (quick TSP), then OSRM provides the actual road geometry.
    """
    # Optimise stop order via Haversine first (fast, good approximation)
    all_coords = np.array(
        [[driver.lat, driver.lon]] + [[o.lat, o.lon] for o in orders]
    )
    tour, _ = nearest_neighbour_tour_haversine(all_coords, start_idx=0)

    # Build waypoints in optimised order
    waypoint_tuples = [(float(all_coords[i, 0]), float(all_coords[i, 1])) for i in tour]
    # Close the loop back to driver start
    waypoint_tuples.append(waypoint_tuples[0])


    try:
        geojson, distance_km, duration_min = (
            await osrm_client.get_route_geometry_and_distance(waypoint_tuples)
        )
    except Exception:
        # OSRM down — fall back to Haversine
        return await _route_haversine(cluster, driver, orders)

    naive_dist = _naive_distance(driver, orders)
    waypoints = _build_waypoints(all_coords, tour, orders)

    return Route(
        id=f"rte_{uuid4().hex[:8]}",
        cluster_id=cluster.id,
        driver_id=driver.id,
        method=RoutingMethod.STREET_NETWORK,
        waypoints=waypoints,
        geojson=geojson,
        total_distance_km=distance_km,
        estimated_duration_minutes=duration_min,
        naive_distance_km=round(naive_dist, 3),
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _naive_distance(driver: Driver, orders: List[Order]) -> float:
    """
    Compute naive distance: separate round trip from driver to each order.
    This is the baseline we compare against.
    """
    total = 0.0
    for order in orders:
        d = haversine_distance(driver.lat, driver.lon, order.lat, order.lon)
        total += d * 2  # round trip
    return total


def _estimate_duration(distance_km: float, avg_speed_kmh: float = 25.0) -> float:
    """Estimate travel duration in minutes given distance and average speed."""
    return (distance_km / avg_speed_kmh) * 60


def _build_waypoints(
    coords: np.ndarray,
    tour: List[int],
    orders: List[Order],
) -> List[RouteWaypoint]:
    """Map tour indices back to RouteWaypoint objects."""
    waypoints = []
    # Index 0 in coords = driver; indices 1..N = orders
    for seq, idx in enumerate(tour):
        order_id = None if idx == 0 else orders[idx - 1].id
        waypoints.append(RouteWaypoint(
            lat=round(float(coords[idx, 0]), 6),
            lon=round(float(coords[idx, 1]), 6),
            order_id=order_id,
            sequence=seq,
        ))
    return waypoints


def _empty_route(cluster: Cluster, driver: Driver, method: RoutingMethod) -> Route:
    return Route(
        id=f"rte_{uuid4().hex[:8]}",
        cluster_id=cluster.id,
        driver_id=driver.id,
        method=method,
        geojson={"type": "Feature", "geometry": {"type": "LineString", "coordinates": []}, "properties": {}},
    )