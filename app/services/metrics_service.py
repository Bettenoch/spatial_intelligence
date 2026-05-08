"""
services/metrics_service.py
─────────────────────────────────────────────────────────────────────────────
Calculates the "before vs after" savings metrics that are the headline
demonstration of this project.

The comparison:
  NAIVE:     Each order = 1 separate driver trip (zero batching)
  OPTIMISED: Clustered orders share one trip per cluster

This delta is what we display on the dashboard as tangible impact:
  - Kilometres saved
  - Litres of fuel saved
  - KES saved
  - kg of CO₂ avoided
  - Minutes saved
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import Dict

from app.core.config import settings
from app.models.route import Route
from app.models.simulation import SimulationMetrics


def calculate_naive_distance(
    order_count: int,
    avg_delivery_distance_km: float = 3.5,
) -> float:
    """
    Estimate the total distance a naive (unoptimised) system would travel.

    Naive assumption: each order requires a separate round-trip from depot.
    Nairobi average delivery radius: ~3.5 km (based on Uber Eats Nairobi data).

    Args:
        order_count:               Total orders in simulation
        avg_delivery_distance_km:  Average one-way distance per delivery

    Returns:
        Total naive distance in km.
    """
    return order_count * avg_delivery_distance_km * 2  # round trip per order


def compute_metrics(
    routes: Dict[str, Route],
    order_count: int,
    existing_metrics: SimulationMetrics,
) -> SimulationMetrics:
    """
    Compute (or update) the full metrics snapshot from current routes.

    Args:
        routes:           All computed routes so far
        order_count:      Total orders in this simulation
        existing_metrics: Previous metrics state (preserves delivery count)

    Returns:
        Updated SimulationMetrics.
    """
    cfg = settings

    # Sum optimised distance across all routes
    optimised_km = sum(r.total_distance_km for r in routes.values())

    # Use pre-stored naive distance on each route if available,
    # otherwise estimate from order count
    naive_km_from_routes = sum(r.naive_distance_km for r in routes.values())
    naive_km_estimate = calculate_naive_distance(order_count)
    naive_km = naive_km_from_routes if naive_km_from_routes > 0 else naive_km_estimate

    # Savings
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