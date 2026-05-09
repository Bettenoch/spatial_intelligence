"""
services/metrics_service.py
─────────────────────────────────────────────────────────────────────────────
Calculates the "before vs after" savings metrics that are the headline
demonstration of this project.

The comparison:
  NAIVE:     Each order = 1 separate driver trip (zero batching)
  OPTIMISED: Clustered orders share one trip per cluster

Fix applied:
  The naive distance must use the SAME distance metric as the optimised
  distance — otherwise we're comparing apples to oranges.

  For street_network: naive uses haversine × circuity factor (1.4) to
  approximate what a naive OSRM route would cost.

  For euclidean/haversine: naive uses the same metric straight-line.

  This ensures savings_percentage is always meaningful and non-zero
  when clustering genuinely helps.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import Dict

from app.core.config import settings
from app.models.route import Route, RoutingMethod
from app.models.simulation import SimulationMetrics

# Average road circuity factor for Nairobi intra-city routes.
# Road distance ≈ 1.4× straight-line distance on average.
# This is used to project haversine naive distances to approximate road distances
# so the comparison is apples-to-apples for street_network mode.
NAIROBI_CIRCUITY_FACTOR = 1.4


def calculate_naive_distance(
    order_count: int,
    avg_delivery_distance_km: float = 3.5,
    method: RoutingMethod = RoutingMethod.HAVERSINE,
) -> float:
    """
    Estimate the total distance a naive (unoptimised) system would travel.

    Naive assumption: each order requires a separate round-trip from depot.

    For street_network mode, we apply the circuity factor so the naive
    baseline is expressed in real road-km, matching the optimised metric.

    Args:
        order_count:               Total orders in simulation
        avg_delivery_distance_km:  Average one-way straight-line distance per delivery
        method:                    Routing method (affects circuity scaling)

    Returns:
        Total naive distance in km.
    """
    straight_line_total = order_count * avg_delivery_distance_km * 2  # round trip per order

    if method == RoutingMethod.STREET_NETWORK:
        return straight_line_total * NAIROBI_CIRCUITY_FACTOR
    return straight_line_total


def compute_metrics(
    routes: Dict[str, Route],
    order_count: int,
    existing_metrics: SimulationMetrics,
    method: RoutingMethod = RoutingMethod.HAVERSINE,
) -> SimulationMetrics:
    """
    Compute (or update) the full metrics snapshot from current routes.

    Args:
        routes:           All computed routes so far
        order_count:      Total orders in this simulation
        existing_metrics: Previous metrics state (preserves delivery count)
        method:           Routing method used (affects naive baseline)

    Returns:
        Updated SimulationMetrics.
    """
    cfg = settings

    # Sum optimised distance across all routes
    optimised_km = sum(r.total_distance_km for r in routes.values())

    # Build naive baseline:
    # 1. Use per-route naive_distance_km if routes have it stored
    # 2. For street_network routes, scale up by circuity factor
    # 3. Fall back to order-count estimate
    naive_km_from_routes = sum(r.naive_distance_km for r in routes.values())

    if naive_km_from_routes > 0:
        # Routes store haversine naive. For street_network, scale to road-km.
        if method == RoutingMethod.STREET_NETWORK:
            naive_km = naive_km_from_routes * NAIROBI_CIRCUITY_FACTOR
        else:
            naive_km = naive_km_from_routes
    else:
        naive_km = calculate_naive_distance(order_count, method=method)

    # Savings — clamp to zero (never report negative savings)
    distance_saved = max(0.0, naive_km - optimised_km)
    fuel_saved = (distance_saved / 100) * cfg.fuel_litres_per_100km
    cost_saved = fuel_saved * cfg.fuel_price_kes_per_litre
    co2_saved = fuel_saved * cfg.co2_kg_per_litre
    # Assume 30 km/h average speed in Nairobi traffic
    time_saved_minutes = (distance_saved / 30) * 60

    return SimulationMetrics(
        deliveries_completed=existing_metrics.deliveries_completed,
        deliveries_total=existing_metrics.deliveries_total,
        optimised_distance_km=round(optimised_km, 2),
        naive_distance_km=round(naive_km, 2),
        distance_saved_km=round(distance_saved, 2),
        fuel_saved_litres=round(fuel_saved, 2),
        cost_saved_kes=round(cost_saved, 0),
        time_saved_minutes=round(time_saved_minutes, 1),
        co2_saved_kg=round(co2_saved, 2),
        active_drivers=existing_metrics.active_drivers,
        clusters_formed=existing_metrics.clusters_formed,
    )


def order_completed(metrics: SimulationMetrics) -> SimulationMetrics:
    """Increment completed delivery counter."""
    return metrics.model_copy(
        update={"deliveries_completed": metrics.deliveries_completed + 1}
    )