"""
services/simulation_service.py
─────────────────────────────────────────────────────────────────────────────
The main simulation orchestrator.

Fixes applied:
  1. Driver assignment: each cluster gets a UNIQUE driver. When there are
     more clusters than drivers, we create virtual "clone" driver entries
     instead of reusing the same driver object (which caused duplicate IDs
     and one driver appearing to make all deliveries).

  2. Metrics: pass routing_method to compute_metrics so the naive baseline
     uses the correct circuity factor for street_network mode.

  3. DRIVER_MOVED events with (0,0) coordinates are rejected before
     broadcasting to prevent map flicker / elements snapping to top-left.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
import random
from copy import deepcopy
from datetime import datetime
from typing import Dict, List
from uuid import uuid4

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
    session_id = state.session_id
    started_at = datetime.utcnow()
    method = RoutingMethod(state.config.routing_method)

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
    session_id = state.session_id
    orders = list(state.orders.values())
    random.shuffle(orders)

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
                    restaurant_name=_pick_restaurant(order.zone, order.order_type),
                ),
            ),
        )
        await asyncio.sleep(0.15)


async def _run_clustering(state: SimulationState) -> SimulationState:
    session_id = state.session_id
    orders = list(state.orders.values())

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

    for cluster in clusters.values():
        for order_id in cluster.order_ids:
            if order_id in state.orders:
                state.orders[order_id].cluster_id = cluster.id
                state.orders[order_id].status = OrderStatus.CLUSTERED

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

    FIX: When there are more clusters than physical drivers, we create
    additional virtual driver entries (clones of the least-loaded driver)
    so every cluster gets a UNIQUE driver_id. This prevents:
      - One driver appearing to make 6+ deliveries
      - Duplicate driver IDs in the legend
      - Color collisions in the route network
    """
    from app.algorithms.distance.haversine import haversine_distance

    real_drivers = list(state.drivers.values())
    clusters = list(state.clusters.values())

    # Sort clusters by size (largest first)
    clusters.sort(key=lambda c: -c.size)

    available_drivers = list(real_drivers)
    assigned_count: Dict[str, int] = {d.id: 0 for d in real_drivers}

    for cluster in clusters:
        if available_drivers:
            # Pick nearest available driver to cluster centroid
            driver = min(
                available_drivers,
                key=lambda d: haversine_distance(
                    d.lat, d.lon, cluster.centroid_lat, cluster.centroid_lon
                ),
            )
            available_drivers.remove(driver)
            assigned_count[driver.id] = assigned_count.get(driver.id, 0) + 1
        else:
            # All real drivers are assigned — create a virtual clone
            # Pick the least-loaded real driver as the template
            template = min(real_drivers, key=lambda d: assigned_count.get(d.id, 0))

            # Clone with a fresh unique ID but same position/zone/name
            new_id = f"drv_{uuid4().hex[:6]}"
            driver = Driver(
                id=new_id,
                name=f"{template.name.split('.')[0]}. #{assigned_count.get(template.id, 0) + 1}",
                lat=template.lat + random.uniform(-0.002, 0.002),
                lon=template.lon + random.uniform(-0.002, 0.002),
                zone=template.zone,
                capacity=template.capacity,
                road_node_id=template.road_node_id,
            )
            state.drivers[new_id] = driver
            assigned_count[template.id] = assigned_count.get(template.id, 0) + 1

        # Assign cluster → driver
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
    session_id = state.session_id
    method = RoutingMethod(state.config.routing_method)

    async def compute_and_broadcast(cluster: Cluster) -> Route:
        driver_id = cluster.driver_id
        if driver_id is None:
            logger.warning(f"  No driver for cluster {cluster.id} — skipping")
            return None
        driver = state.drivers.get(driver_id)
        if not driver:
            logger.warning(f"  Driver {driver_id} not found — skipping")
            return None

        route = await compute_route(cluster, driver, state.orders, method)
        state.routes[route.id] = route
        driver.total_distance_km += route.total_distance_km
        driver.status = DriverStatus.EN_ROUTE

        await ws_manager.broadcast(
            session_id,
            RouteComputedEvent(
                session_id=session_id,
                data=RouteComputedEvent.Data(
                    route_id=route.id,
                    cluster_id=cluster.id,
                    driver_id=driver.id,
                    driver_name=driver.name,
                    method=str(method.value),
                    geojson=route.geojson or {},
                    total_distance_km=route.total_distance_km,
                    estimated_duration_minutes=route.estimated_duration_minutes,
                    naive_distance_km=route.naive_distance_km,
                    color=cluster.color,
                ),
            ),
        )

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

    tasks = [
        compute_and_broadcast(cluster)
        for cluster in state.clusters.values()
        if cluster.driver_id
    ]
    await asyncio.gather(*tasks)

    # Pass method so naive baseline uses correct circuity scaling
    state.metrics = compute_metrics(
        state.routes,
        len(state.orders),
        state.metrics,
        method=method,
    )
    await _broadcast_metrics(state)

    return state


async def _animate_deliveries(state: SimulationState) -> SimulationState:
    session_id = state.session_id
    ANIMATION_STEPS = 10

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

        for oid in cluster.order_ids:
            if oid in state.orders:
                state.orders[oid].status = OrderStatus.IN_TRANSIT

        waypoints = route.waypoints
        total_steps = len(waypoints) * ANIMATION_STEPS

        for wp_idx, wp in enumerate(waypoints):
            next_wp = waypoints[wp_idx + 1] if wp_idx + 1 < len(waypoints) else wp

            for step in range(ANIMATION_STEPS):
                t = step / ANIMATION_STEPS
                interp_lat = wp.lat + (next_wp.lat - wp.lat) * t
                interp_lon = wp.lon + (next_wp.lon - wp.lon) * t
                progress = (wp_idx * ANIMATION_STEPS + step) / max(total_steps, 1)

                # FIX: reject zero/invalid coordinates before broadcasting
                if not (interp_lat and interp_lon) or (interp_lat == 0 and interp_lon == 0):
                    continue

                await ws_manager.broadcast(
                    session_id,
                    DriverMovedEvent(
                        session_id=session_id,
                        data=DriverMovedEvent.Data(
                            driver_id=driver.id,
                            driver_name=driver.name,
                            lat=round(interp_lat, 6),
                            lon=round(interp_lon, 6),
                            progress_pct=round(progress, 3),
                            current_order_id=wp.order_id,
                        ),
                    ),
                )
                await asyncio.sleep(0.08)

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


# ── Restaurant name picker (for hover tooltips) ───────────────────────────────

_RESTAURANTS: Dict[str, List[str]] = {
    "CBD":         ["Java House CBD", "Chicken Inn OTC", "KFC Moi Avenue", "Steers CBD", "Pizza Inn"],
    "Westlands":   ["The Alchemist", "Chicken Inn Westlands", "Artcaffe Westlands", "Burger Hut", "Sushi Platter"],
    "Kilimani":    ["Pili Pili", "Mediterraneo", "Bistro 6", "The Local", "K1 Fry"],
    "Lavington":   ["About Thyme", "Sippers", "Talisman", "Jungle Grill"],
    "Karen":       ["Karen Blixen Coffee", "Talisman Karen", "Cultiva", "Brew Bistro Karen"],
    "Parklands":   ["Habesha", "Swahili Plate", "Javas Parklands", "Mama Oliech"],
    "Eastleigh":   ["Somali Kitchen", "City Plate", "Eastleigh Grill", "Royal Biryani"],
    "Upper Hill":  ["Kaldis Coffee", "Javas Upper Hill", "Epicure", "Urban Eatery"],
    "Kasarani":    ["Zen Garden", "Kasarani Grill", "Safari Inn", "Nandos Kasarani"],
    "South C":     ["Smoke & Grill", "Nakumatt Junction Resto", "South C Eats"],
    "Hurlingham":  ["Nairobi Java Hurlingham", "Grill House", "Pronto Hurlingham"],
    "Rongai":      ["Rongai Jikos", "Roadside Grill", "Nakuru Point"],
    "Roysambu":    ["Roysambu Kitchen", "Nandos Roysambu", "Westpoint Grill"],
    "Pangani":     ["Pangani Grill", "Tasty Bites Pangani"],
    "Lang'ata":    ["Carnivore", "Ndege View Grill", "Lang'ata Eats"],
    "Milimani":    ["Cafe Maghreb", "Milimani Kitchen"],
    "Muthaiga":    ["Muthaiga Country Club", "Patio Café"],
    "Buruburu":    ["Buruburu Grill", "Mambo Kitchen", "Casa Bianca"],
    "Githurai":    ["Githurai Grill", "Mama Africa", "Githurai Bites"],
    "Ongata Rongai": ["Rongai Grill", "Safari Eats"],
}
_DEFAULT_RESTAURANTS = ["Nairobi Eats", "The Local Kitchen", "Quick Bites", "Urban Grill"]


def _pick_restaurant(zone: str, order_type: str) -> str:
    options = _RESTAURANTS.get(zone, _DEFAULT_RESTAURANTS)
    return random.choice(options)