"""
simulation/scenario_builder.py
─────────────────────────────────────────────────────────────────────────────
Assembles a complete simulation scenario from config parameters.
Thin orchestration layer — delegates generation to specialised generators.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from loguru import logger

from app.models.simulation import SimulationConfig, SimulationState, SimulationStatus
from app.simulation.driver_generator import generate_drivers
from app.simulation.order_generator import generate_orders


def build_scenario(config: SimulationConfig) -> SimulationState:
    """
    Create a new SimulationState from the given config.

    This is called once when a /simulate request is received.
    The state is then handed off to simulation_service for processing.
    """
    logger.info(
        f"🎬 Building scenario: {config.scenario_label} | "
        f"{config.order_count} orders, {config.driver_count} drivers, "
        f"method={config.routing_method}"
    )

    state = SimulationState(config=config)
    state.status = SimulationStatus.GENERATING_ORDERS

    # Generate orders
    orders = generate_orders(count=config.order_count)
    state.orders = {o.id: o for o in orders}
    state.metrics.deliveries_total = len(orders)

    # Generate drivers
    drivers = generate_drivers(count=config.driver_count)
    state.drivers = {d.id: d for d in drivers}
    state.metrics.active_drivers = len(drivers)

    logger.info(
        f"  ✅ Scenario ready: session={state.session_id} | "
        f"{len(state.orders)} orders, {len(state.drivers)} drivers"
    )
    return state