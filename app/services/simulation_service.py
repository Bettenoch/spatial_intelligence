"""
services/simulation_service.py
─────────────────────────────────────────────────────────────────────────────
The main simulation orchestrator.

This is the conductor — it coordinates:
  1. Order generation (already done in scenario_builder)
  2. Broadcasting orders to the frontend one-by-one (animated pin drops)
  3. DBSCAN clustering of orders
  4. Assigning drivers to clusters
  5. Computing routes for each cluster (in parallel)
  6. Broadcasting routes and driver assignments
  7. Simulating driver movement along routes
  8. Updating and broadcasting metrics after each delivery

All heavy computation runs in thread pools (via run_in_executor) so the
event loop never blocks and WebSocket messages keep flowing.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Dict, List

from loguru import logger

from app.algorithms.clustering.dbscan import run_dbscan
from app.core.config import settings
from app.models.cluster import Cluster
from app.models.driver import Driver, DriverStatus
from app.models.order import Order, OrderStatus
from app.models.route import Route, RoutingMethod
from app.models.simulation import SimulationState, SimulationStatus
from app.services.metrics_service import compute_metrics, order_completed
from app.services.routing_service import compute_route
from app.websocket.events import (
    ClusterFormedEvent,
    DeliveryCompletedEvent,
    DriverAssignedEvent,
    DriverMovedEvent,
    MetricsUpdatedEvent,
    OrderCreatedEvent,
    OrderStatusChangedEvent,
    RouteComputedEvent,
    SimulationCompletedEvent,
    SimulationStatusEvent,
)
from app.websocket.manager import ws_manager


async def run_simulation(state: SimulationState) -> SimulationState:
    """
    Execute the full simulation pipeline for a given state.

    Args:
        state: Pre-built SimulationState from scenario_builder

    Returns:
        Final state with all routes, clusters, and metrics populated.
    """
    session_id = state.session_id
    started_at = datetime.utcnow()

    try:
        # ── Phase 1: Broadcast orders appearing on the map ────────────────
        await _broadcast_status(session_id, "generating_orders", "Generating delivery orders across Nairobi…")
        state.status = SimulationStatus.GENERATING_ORDERS
        await _broadcast_orders(state)

        # ── Phase 2: Cluster orders ───────────────────────────────────────
        await _broadcast_status(session_id, "clustering", "Clustering nearby orders with DBSCAN…")
        state.status = SimulationStatus.CLUSTERING
        state = await _run_clustering(state)

        # ── Phase 3: Assign drivers to clusters ──────────────────────────
        state = _assign_drivers_to_clusters(state)

        # ── Phase 4: Compute routes (parallel) ────────────────────────────
        await _broadcast_status(session_id, "routing", f"Computing {state.config.routing_method} routes…")
        state.status = SimulationStatus.ROUTING
        state = await _compute_routes(state)

        # ── Phase 5: Animate drivers + update metrics ─────────────────────
        await _broadcast_status(session_id, "animating", "Drivers are on their way…")
        state.status = SimulationStatus.ANIMATING
        state = await _animate_deliveries(state)

        # ── Phase 6: Final summary ────────────────────────────────────────
        state.status = SimulationStatus.COMPLETED
        state.completed_at = datetime.utcnow()
        duration = (state.completed_at - started_at).total_seconds()

        await ws_manager.broadcast(
            session_id,
            SimulationCompletedEvent(
                session_id=session_id,
                data=SimulationCompletedEvent.Data(
                    session_id=session_id,
                    total_deliveries=state.metrics.deliveries_completed,
                    total_distance_km=state.metrics.optimised_distance_km,
                    total_savings_pct=state.metrics.savings_percentage,
                    duration_seconds=round(duration, 1),
                ),
            ),
        )
        logger.info(
            f"✅ Simulation {session_id} complete — "
            f"{state.metrics.deliveries_completed} deliveries, "
            f"{state.metrics.savings_percentage}% savings"
        )

    except Exception as exc:
        logger.error(f"Simulation {session_id} failed: {exc}", exc_info=True)
        state.status = SimulationStatus.FAILED
        state.error_message = str(exc)

    return state


# ── Phase implementations ────────────────────────────────────────────────────

async def _broadcast_orders(state: SimulationState) -> None:
    """Stream orders to the frontend with a small delay between each."""
    session_id = state.session_id
    orders = list(state.orders.values())
    random.shuffle(orders)  # randomise appearance order for visual effect

    for order in orders:
        await ws_manager.broadcast(
            session_id,
            OrderCreatedEvent(
                session_id=session_id,
                data=OrderCreatedEvent.Data(
                    order_id=order.id,
                    lat=order.lat,
                    lon=order.lon,
                    zone=order.zone,
                    order_type=order.order_type,
                    estimated_prep_minutes=order.estimated_prep_minutes,
                ),
            ),
        )
        await asyncio.sleep(0.15)  # 150ms between pin drops → cinematic effect


async def _run_clustering(state: SimulationState) -> SimulationState:
    """Run DBSCAN in a thread pool and broadcast resulting clusters."""
    session_id = state.session_id
    orders = list(state.orders.values())

    # Run blocking clustering in thread pool
    loop = asyncio.get_event_loop()
    clusters: Dict[str, Cluster] = await loop.run_in_executor(
        None,
        lambda: run_dbscan(
            orders,
            epsilon_km=settings.dbscan_epsilon_km,
            min_samples=settings.dbscan_min_samples,
            max_cluster_size=settings.max_orders_per_driver,
        ),
    )

    state.clusters = clusters
    state.metrics.clusters_formed = len(clusters)

    # Update order status and cluster assignment
    for cluster in clusters.values():
        for order_id in cluster.order_ids:
            if order_id in state.orders:
                state.orders[order_id].cluster_id = cluster.id
                state.orders[order_id].status = OrderStatus.CLUSTERED

    # Broadcast clusters to frontend
    for cluster in clusters.values():
        await ws_manager.broadcast(
            session_id,
            ClusterFormedEvent(
                session_id=session_id,
                data=ClusterFormedEvent.Data(
                    cluster_id=cluster.id,
                    order_ids=cluster.order_ids,
                    centroid_lat=cluster.centroid_lat,
                    centroid_lon=cluster.centroid_lon,
                    color=cluster.color,
                    zone_label=cluster.zone_label,
                    size=cluster.size,
                ),
            ),
        )
        await asyncio.sleep(0.1)

    return state


def _assign_drivers_to_clusters(state: SimulationState) -> SimulationState:
    """
    Greedy assignment: assign nearest available driver to each cluster.
    """
    from app.algorithms.distance.haversine import haversine_distance

    drivers = list(state.drivers.values())
    clusters = list(state.clusters.values())

    # Sort clusters by size (largest first — prioritise big clusters)
    clusters.sort(key=lambda c: -c.size)

    available_drivers = list(drivers)

    for cluster in clusters:
        if not available_drivers:
            # More clusters than drivers — last driver takes remaining
            driver = drivers[-1] if drivers else None
        else:
            # Find closest available driver to cluster centroid
            driver = min(
                available_drivers,
                key=lambda d: haversine_distance(
                    d.lat, d.lon, cluster.centroid_lat, cluster.centroid_lon
                ),
            )
            available_drivers.remove(driver)

        if driver:
            cluster.driver_id = driver.id
            driver.cluster_id = cluster.id
            driver.assigned_orders = cluster.order_ids
            driver.status = DriverStatus.ASSIGNED

            for order_id in cluster.order_ids:
                if order_id in state.orders:
                    state.orders[order_id].driver_id = driver.id
                    state.orders[order_id].status = OrderStatus.ASSIGNED

    return state


async def _compute_routes(state: SimulationState) -> SimulationState:
    """Compute routes for all clusters in parallel, broadcast each as it completes."""
    session_id = state.session_id
    method = RoutingMethod(state.config.routing_method)

    async def compute_and_broadcast(cluster: Cluster) -> Route:
        driver_id = cluster.driver_id
        if driver_id is None:
            logger.warning(f"  No driver for cluster {cluster.id} — skipping")
            return None
        driver = state.drivers.get(driver_id)
        if not driver:
            logger.warning(f"  No driver for cluster {cluster.id} — skipping")
            return None

        route = await compute_route(cluster, driver, state.orders, method)
        state.routes[route.id] = route
        driver.total_distance_km += route.total_distance_km
        driver.status = DriverStatus.EN_ROUTE

        # Broadcast the computed route
        await ws_manager.broadcast(
            session_id,
            RouteComputedEvent(
                session_id=session_id,
                data=RouteComputedEvent.Data(
                    route_id=route.id,
                    cluster_id=cluster.id,
                    driver_id=driver.id,
                    method=str(method.value),
                    geojson=route.geojson or {},
                    total_distance_km=route.total_distance_km,
                    estimated_duration_minutes=route.estimated_duration_minutes,
                    naive_distance_km=route.naive_distance_km,
                    color=cluster.color,
                ),
            ),
        )

        # Broadcast driver assignment
        await ws_manager.broadcast(
            session_id,
            DriverAssignedEvent(
                session_id=session_id,
                data=DriverAssignedEvent.Data(
                    driver_id=driver.id,
                    driver_name=driver.name,
                    cluster_id=cluster.id,
                    order_count=len(cluster.order_ids),
                ),
            ),
        )

        return route

    # Run all route computations concurrently
    tasks = [
        compute_and_broadcast(cluster)
        for cluster in state.clusters.values()
        if cluster.driver_id
    ]
    await asyncio.gather(*tasks)

    # Update metrics after all routes computed
    state.metrics = compute_metrics(
        state.routes,
        len(state.orders),
        state.metrics,
    )
    await _broadcast_metrics(state)

    return state


async def _animate_deliveries(state: SimulationState) -> SimulationState:
    """
    Simulate driver movement along routes.
    Broadcasts DRIVER_MOVED events at intervals to animate map icons.
    Each order completed increments the deliveries counter.
    """
    session_id = state.session_id
    ANIMATION_STEPS = 10  # number of intermediate position broadcasts

    for cluster in state.clusters.values():
        driver_id = cluster.driver_id
        driver = state.drivers.get(driver_id)
        if not driver:
            continue

        route = next(
            (r for r in state.routes.values() if r.cluster_id == cluster.id),
            None,
        )
        if not route or not route.waypoints:
            continue

        # Update order status to IN_TRANSIT
        for oid in cluster.order_ids:
            if oid in state.orders:
                state.orders[oid].status = OrderStatus.IN_TRANSIT

        waypoints = route.waypoints
        total_steps = len(waypoints) * ANIMATION_STEPS

        for wp_idx, wp in enumerate(waypoints):
            # Interpolate between current and next waypoint
            next_wp = waypoints[wp_idx + 1] if wp_idx + 1 < len(waypoints) else wp

            for step in range(ANIMATION_STEPS):
                t = step / ANIMATION_STEPS
                interp_lat = wp.lat + (next_wp.lat - wp.lat) * t
                interp_lon = wp.lon + (next_wp.lon - wp.lon) * t
                progress = (wp_idx * ANIMATION_STEPS + step) / max(total_steps, 1)

                await ws_manager.broadcast(
                    session_id,
                    DriverMovedEvent(
                        session_id=session_id,
                        data=DriverMovedEvent.Data(
                            driver_id=driver.id,
                            lat=round(interp_lat, 6),
                            lon=round(interp_lon, 6),
                            progress_pct=round(progress, 3),
                            current_order_id=wp.order_id,
                        ),
                    ),
                )
                await asyncio.sleep(0.08)  # ~12.5 frames/second

            # Mark delivery complete when reaching a stop
            if wp.order_id and wp.order_id in state.orders:
                order = state.orders[wp.order_id]
                order.status = OrderStatus.DELIVERED
                order.delivered_at = datetime.utcnow()
                driver.deliveries_completed += 1

                delivery_time = (
                    (order.delivered_at - order.created_at).total_seconds() / 60
                )

                await ws_manager.broadcast(
                    session_id,
                    DeliveryCompletedEvent(
                        session_id=session_id,
                        data=DeliveryCompletedEvent.Data(
                            order_id=order.id,
                            driver_id=driver.id,
                            time_taken_minutes=round(delivery_time, 1),
                        ),
                    ),
                )

                state.metrics = order_completed(state.metrics)
                await _broadcast_metrics(state)

        driver.status = DriverStatus.COMPLETED

    return state


# ── Utility ──────────────────────────────────────────────────────────────────

async def _broadcast_status(session_id: str, status: str, message: str) -> None:
    await ws_manager.broadcast(
        session_id,
        SimulationStatusEvent(
            session_id=session_id,
            data=SimulationStatusEvent.Data(status=status, message=message),
        ),
    )


async def _broadcast_metrics(state: SimulationState) -> None:
    m = state.metrics
    await ws_manager.broadcast(
        state.session_id,
        MetricsUpdatedEvent(
            session_id=state.session_id,
            data=MetricsUpdatedEvent.Data(
                deliveries_completed=m.deliveries_completed,
                deliveries_total=m.deliveries_total,
                optimised_distance_km=m.optimised_distance_km,
                naive_distance_km=m.naive_distance_km,
                distance_saved_km=m.distance_saved_km,
                savings_percentage=m.savings_percentage,
                fuel_saved_litres=m.fuel_saved_litres,
                cost_saved_kes=m.cost_saved_kes,
                time_saved_minutes=m.time_saved_minutes,
                co2_saved_kg=m.co2_saved_kg,
                active_drivers=m.active_drivers,
                clusters_formed=m.clusters_formed,
            ),
        ),
    )