"""
simulation/scenario_builder.py — UPDATED
─────────────────────────────────────────────────────────────────────────────
Changes:
  - Generates restaurants first
  - Passes restaurants to order generator so each order has a source
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from loguru import logger

from app.models.simulation import SimulationConfig, SimulationState, SimulationStatus
from app.simulation.driver_generator import generate_drivers
from app.simulation.order_generator import generate_orders
from app.simulation.restaurant_generator import generate_restaurants


def build_scenario(config: SimulationConfig) -> SimulationState:
    """
    Create a new SimulationState from the given config.
    """
    logger.info(
        f"🎬 Building scenario: {config.scenario_label} | "
        f"{config.order_count} orders, {config.driver_count} drivers, "
        f"{config.restaurant_count} restaurants, "
        f"method={config.routing_method}"
    )

    state = SimulationState(config=config)
    state.status = SimulationStatus.GENERATING_ORDERS

    # 1. Generate restaurants first
    restaurants = generate_restaurants(count=config.restaurant_count)
    state.restaurants = {r.id: r for r in restaurants}

    # 2. Generate orders — each assigned to nearest restaurant
    orders = generate_orders(count=config.order_count, restaurants=restaurants)
    state.orders = {o.id: o for o in orders}
    state.metrics.deliveries_total = len(orders)

    # 3. Generate drivers
    drivers = generate_drivers(count=config.driver_count)
    state.drivers = {d.id: d for d in drivers}
    state.metrics.active_drivers = len(drivers)

    logger.info(
        f"  ✅ Scenario ready: session={state.session_id} | "
        f"{len(state.orders)} orders, {len(state.drivers)} drivers, "
        f"{len(state.restaurants)} restaurants"
    )
    return state