"""
services/simulation_service.py — WITH TIMING DIAGNOSTICS

"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from loguru import logger

from app.core.config import settings
from app.models.cluster import Cluster
from app.models.driver import Driver, DriverStatus
from app.models.order import Order, OrderStatus
from app.models.route import Route
from app.models.simulation import (
    DeliveryRecord,
    SimulationMetrics,
    SimulationState,
    SimulationStatus,
)
from app.services.metrics_service import compute_metrics, order_completed
from app.services.routing_service import compute_route
from app.websocket.events import (
    ClusterFormedEvent,
    DeliveryCompletedEvent,
    DeliveryRecord as WSDeliveryRecord,
    DeliveryTableEvent,
    DriverAssignedEvent,
    DriverMovedEvent,
    MetricsUpdatedEvent,
    OrderCreatedEvent,
    OrderStatusChangedEvent,
    RestaurantCreatedEvent,
    RouteComputedEvent,
    SimulationCompletedEvent,
    SimulationStartedEvent,
    SimulationStatusEvent,
)
from app.websocket.manager import ws_manager

DRIVER_COLORS = [
    "#00ccff", "#FF6B35", "#7fff00", "#DDA0DD", "#4ECDC4",
    "#ffaa00", "#ff4d6d", "#85C1E9", "#F7DC6F", "#BB8FCE",
]


def _utc_now() -> datetime:
    """Return current UTC time as a NAIVE datetime (no tzinfo)."""
    return datetime.utcnow()


def _driver_color(idx: int) -> str:
    return DRIVER_COLORS[idx % len(DRIVER_COLORS)]


# ── Timing helper ─────────────────────────────────────────────────────────────

def _ts(t0: float, label: str, session: str, detail: str = "") -> None:
    """
    Emit a timing log line.

    Format:  [sim_xxx] ⏱ +12.34s  LABEL  (detail)

    t0   — time.perf_counter() captured at the very start of run_simulation
    """
    elapsed = time.perf_counter() - t0
    suffix = f"  ({detail})" if detail else ""
    logger.info(f"[{session}] ⏱ +{elapsed:.2f}s  {label}{suffix}")


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_simulation(state: SimulationState) -> SimulationState:
    speed = state.config.simulation_speed
    session = state.session_id
    config = state.config
    started_at = _utc_now()

    # ── T0: clock starts the moment run_simulation is entered ────────────────
    t0 = time.perf_counter()
    _ts(t0, "RUN_SIMULATION_ENTERED", session,
        f"orders={len(state.orders)} drivers={len(state.drivers)} "
        f"restaurants={len(state.restaurants)} method={config.routing_method}")

    # ── Wait for WebSocket client ─────────────────────────────────────────────
    _ts(t0, "WS_WAIT_START", session, "polling for client connection (max 3s)")
    wait_start = time.perf_counter()

    for i in range(200):  # 200 × 50ms = 10s max wait
        if ws_manager.connection_count(session) > 0:
            waited_ms = (time.perf_counter() - wait_start) * 1000
            _ts(t0, "WS_CLIENT_CONNECTED", session,
                f"client arrived after {waited_ms:.0f}ms (poll #{i})")
            break
        await asyncio.sleep(0.05)
    else:
        waited_ms = (time.perf_counter() - wait_start) * 1000
        logger.warning(
            f"[{session}] No client connected after {waited_ms:.0f}ms — proceeding anyway"
        )
        _ts(t0, "WS_TIMEOUT_PROCEEDING", session,
            "all early events will broadcast to 0 clients")

    # ── Phase 0: Started ──────────────────────────────────────────────────────
    _ts(t0, "PHASE_0_SIMULATION_STARTED_EVENT", session)
    await ws_manager.broadcast(
        session,
        SimulationStartedEvent(
            session_id=session,
            data=SimulationStartedEvent.Data(
                session_id=session,
                order_count=len(state.orders),
                driver_count=len(state.drivers),
                restaurant_count=len(state.restaurants),
                routing_method=config.routing_method,
                scenario_label=config.scenario_label,
            ),
        ),
    )

    # ── Phase 1: Emit restaurants ─────────────────────────────────────────────
    _ts(t0, "PHASE_1_RESTAURANTS_START", session,
        f"emitting {len(state.restaurants)} restaurants")
    await ws_manager.broadcast(
        session,
        SimulationStatusEvent(
            session_id=session,
            data=SimulationStatusEvent.Data(
                status="generating_orders",
                message=f"Placing {len(state.restaurants)} restaurants…",
            ),
        ),
    )
    for rest in state.restaurants.values():
        await ws_manager.broadcast(
            session,
            RestaurantCreatedEvent(
                session_id=session,
                data=RestaurantCreatedEvent.Data(
                    restaurant_id=rest.id,
                    name=rest.name,
                    lat=rest.lat,
                    lon=rest.lon,
                    zone=rest.zone,
                    cuisine_type=rest.cuisine_type,
                ),
            ),
        )
        await asyncio.sleep(0.05 / speed)

    _ts(t0, "PHASE_1_RESTAURANTS_DONE", session)

    # ── Phase 2: Emit orders ──────────────────────────────────────────────────
    _ts(t0, "PHASE_2_ORDERS_START", session,
        f"emitting {len(state.orders)} orders")
    for order in state.orders.values():
        await ws_manager.broadcast(
            session,
            OrderCreatedEvent(
                session_id=session,
                data=OrderCreatedEvent.Data(
                    order_id=order.id,
                    lat=order.lat,
                    lon=order.lon,
                    zone=order.zone,
                    order_type=order.order_type,
                    estimated_prep_minutes=order.estimated_prep_minutes,
                    restaurant_name=order.restaurant_name,
                    restaurant_id=order.restaurant_id,
                    restaurant_lat=order.restaurant_lat,
                    restaurant_lon=order.restaurant_lon,
                    restaurant_zone=order.restaurant_zone,
                    ordered_at=order.ordered_at,
                ),
            ),
        )
        await asyncio.sleep(0.04 / speed)

    _ts(t0, "PHASE_2_ORDERS_DONE", session)

    # ── Phase 3: Cluster ──────────────────────────────────────────────────────
    state.status = SimulationStatus.CLUSTERING
    _ts(t0, "PHASE_3_CLUSTERING_START", session,
        f"DBSCAN on {len(state.orders)} orders")
    await ws_manager.broadcast(
        session,
        SimulationStatusEvent(
            session_id=session,
            data=SimulationStatusEvent.Data(
                status="clustering", message="Clustering nearby orders with DBSCAN…"
            ),
        ),
    )

    cluster_start = time.perf_counter()
    clusters = _cluster_orders(state)
    cluster_ms = (time.perf_counter() - cluster_start) * 1000

    state.clusters = clusters
    state.metrics.clusters_formed = len(clusters)
    _ts(t0, "PHASE_3_CLUSTERING_DONE", session,
        f"{len(clusters)} clusters in {cluster_ms:.0f}ms")

    for cluster in clusters.values():
        await ws_manager.broadcast(
            session,
            ClusterFormedEvent(
                session_id=session,
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
        for oid in cluster.order_ids:
            if oid in state.orders:
                order = state.orders[oid]
                order.cluster_id = cluster.id
                order.status = OrderStatus.CLUSTERED
                state.orders[oid] = order
        await asyncio.sleep(0.06 / speed)

    # ── Phase 4: Assign drivers & compute routes ──────────────────────────────
    state.status = SimulationStatus.ROUTING
    _ts(t0, "PHASE_4_ROUTING_START", session,
        f"{len(clusters)} clusters → {len(state.drivers)} drivers "
        f"method={config.routing_method}")
    await ws_manager.broadcast(
        session,
        SimulationStatusEvent(
            session_id=session,
            data=SimulationStatusEvent.Data(
                status="routing", message="Computing optimised routes…"
            ),
        ),
    )

    driver_list = list(state.drivers.values())
    cluster_list = list(clusters.values())

    driver_color_map: Dict[str, str] = {}
    for idx, driver in enumerate(driver_list):
        driver_color_map[driver.id] = _driver_color(idx)

    assignments: Dict[str, List[Cluster]] = {d.id: [] for d in driver_list}
    for i, cluster in enumerate(cluster_list):
        assigned_driver = driver_list[i % len(driver_list)]
        assignments[assigned_driver.id].append(cluster)
        cluster.driver_id = assigned_driver.id

    routes: Dict[str, Route] = {}
    route_count = 0

    for driver in driver_list:
        driver_clusters = assignments[driver.id]
        if not driver_clusters:
            continue
        color = driver_color_map[driver.id]

        for cluster in driver_clusters:
            driver.status = DriverStatus.ASSIGNED
            driver.cluster_id = cluster.id
            state.drivers[driver.id] = driver

            await ws_manager.broadcast(
                session,
                DriverAssignedEvent(
                    session_id=session,
                    data=DriverAssignedEvent.Data(
                        driver_id=driver.id,
                        driver_name=driver.name,
                        cluster_id=cluster.id,
                        order_count=cluster.size,
                    ),
                ),
            )

            for oid in cluster.order_ids:
                if oid in state.orders:
                    order = state.orders[oid]
                    order.status = OrderStatus.ASSIGNED
                    order.driver_id = driver.id
                    state.orders[oid] = order
                    await ws_manager.broadcast(
                        session,
                        OrderStatusChangedEvent(
                            session_id=session,
                            data=OrderStatusChangedEvent.Data(
                                order_id=oid,
                                status="assigned",
                                driver_id=driver.id,
                            ),
                        ),
                    )

            route_start = time.perf_counter()
            route = await compute_route(
                cluster=cluster,
                driver=driver,
                orders=state.orders,
                method=config.routing_method,
            )
            route_ms = (time.perf_counter() - route_start) * 1000
            route_count += 1

            _ts(t0, f"ROUTE_{route_count}_COMPUTED", session,
                f"driver={driver.name} cluster={cluster.zone_label!r} "
                f"orders={cluster.size} dist={route.total_distance_km:.2f}km "
                f"took={route_ms:.0f}ms")

            route = route.model_copy(
                update={"color": color, "driver_name": driver.name}
            )
            routes[route.id] = route
            state.routes[route.id] = route

            await ws_manager.broadcast(
                session,
                RouteComputedEvent(
                    session_id=session,
                    data=RouteComputedEvent.Data(
                        route_id=route.id,
                        cluster_id=cluster.id,
                        driver_id=driver.id,
                        driver_name=driver.name,
                        method=route.method,
                        geojson=route.geojson or {},
                        total_distance_km=route.total_distance_km,
                        estimated_duration_minutes=route.estimated_duration_minutes,
                        naive_distance_km=route.naive_distance_km,
                        color=color,
                    ),
                ),
            )

            state.metrics = compute_metrics(
                routes=routes,
                order_count=len(state.orders),
                existing_metrics=state.metrics,
                method=config.routing_method,
            )
            await _emit_metrics(session, state.metrics)
            await asyncio.sleep(0.1 / speed)

    _ts(t0, "PHASE_4_ROUTING_DONE", session,
        f"{route_count} routes computed total")

    # ── Phase 5: Animate deliveries ───────────────────────────────────────────
    state.status = SimulationStatus.ANIMATING
    _ts(t0, "PHASE_5_ANIMATION_START", session,
        f"{len(driver_list)} driver animation tasks")
    await ws_manager.broadcast(
        session,
        SimulationStatusEvent(
            session_id=session,
            data=SimulationStatusEvent.Data(
                status="animating", message="Drivers en route…"
            ),
        ),
    )

    delivery_records: List[DeliveryRecord] = []

    animation_tasks = []
    for driver in driver_list:
        driver_clusters = assignments[driver.id]
        if driver_clusters:
            task = asyncio.create_task(
                _animate_driver(
                    session=session,
                    driver=driver,
                    clusters=driver_clusters,
                    orders=state.orders,
                    routes=routes,
                    state=state,
                    color=driver_color_map[driver.id],
                    delivery_records=delivery_records,
                    speed=config.simulation_speed,
                )
            )
            animation_tasks.append(task)

    results = await asyncio.gather(*animation_tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                f"Animation task {i} failed: {type(result).__name__}: {result}"
            )

    state.delivery_records = delivery_records
    _ts(t0, "PHASE_5_ANIMATION_DONE", session,
        f"{len(delivery_records)} deliveries recorded")

    # ── Phase 6: Complete ─────────────────────────────────────────────────────
    state.status = SimulationStatus.COMPLETED
    state.completed_at = _utc_now()
    duration = (_utc_now() - started_at).total_seconds()

    total_deliveries = sum(d.deliveries_completed for d in state.drivers.values())

    state.metrics = compute_metrics(
        routes=routes,
        order_count=len(state.orders),
        existing_metrics=state.metrics,
        method=config.routing_method,
    )
    state.metrics = state.metrics.model_copy(
        update={"deliveries_completed": total_deliveries}
    )
    await _emit_metrics(session, state.metrics)

    ws_records = [
        WSDeliveryRecord(
            order_id=r.order_id,
            driver_name=r.driver_name,
            restaurant_name=r.restaurant_name,
            restaurant_zone=r.restaurant_zone,
            customer_zone=r.customer_zone,
            ordered_at=r.ordered_at.isoformat() if r.ordered_at else None,
            delivered_at=r.delivered_at.isoformat() if r.delivered_at else None,
            duration_minutes=r.duration_minutes,
            distance_km=r.distance_km,
            algorithm=r.algorithm,
            status=r.status,
        )
        for r in delivery_records
    ]

    await ws_manager.broadcast(
        session,
        DeliveryTableEvent(
            session_id=session,
            data=DeliveryTableEvent.Data(
                records=ws_records, total_count=len(ws_records)
            ),
        ),
    )

    savings_pct = state.metrics.savings_percentage
    _ts(t0, "PHASE_6_COMPLETE", session,
        f"{len(delivery_records)} deliveries savings={savings_pct:.1f}% "
        f"wall_clock={duration:.1f}s")

    logger.info(
        f"✅ Simulation {session} complete — "
        f"{len(delivery_records)} deliveries, {savings_pct:.1f}% savings"
    )

    await ws_manager.broadcast(
        session,
        SimulationCompletedEvent(
            session_id=session,
            data=SimulationCompletedEvent.Data(
                session_id=session,
                total_deliveries=len(delivery_records),
                total_distance_km=state.metrics.optimised_distance_km,
                total_savings_pct=savings_pct,
                duration_seconds=round(duration, 1),
            ),
        ),
    )

    return state


# ── Internal helpers ──────────────────────────────────────────────────────────


def _cluster_orders(state: SimulationState) -> Dict[str, Cluster]:
    from app.algorithms.clustering.dbscan import run_dbscan

    return run_dbscan(
        orders=list(state.orders.values()),
        epsilon_km=settings.dbscan_epsilon_km,
        min_samples=settings.dbscan_min_samples,
        max_cluster_size=settings.max_orders_per_driver,
    )


async def _emit_metrics(session: str, metrics: SimulationMetrics) -> None:
    await ws_manager.broadcast(
        session,
        MetricsUpdatedEvent(
            session_id=session,
            data=MetricsUpdatedEvent.Data(
                deliveries_completed=metrics.deliveries_completed,
                deliveries_total=metrics.deliveries_total,
                optimised_distance_km=metrics.optimised_distance_km,
                naive_distance_km=metrics.naive_distance_km,
                distance_saved_km=metrics.distance_saved_km,
                savings_percentage=metrics.savings_percentage,
                fuel_saved_litres=metrics.fuel_saved_litres,
                cost_saved_kes=metrics.cost_saved_kes,
                time_saved_minutes=metrics.time_saved_minutes,
                co2_saved_kg=metrics.co2_saved_kg,
                active_drivers=metrics.active_drivers,
                clusters_formed=metrics.clusters_formed,
            ),
        ),
    )


async def _animate_driver(
    session: str,
    driver: Driver,
    clusters: List[Cluster],
    orders: Dict[str, Order],
    routes: Dict[str, Route],
    state: SimulationState,
    color: str,
    delivery_records: List[DeliveryRecord],
    speed: float = 1.0,
) -> None:
    driver.status = DriverStatus.EN_ROUTE
    state.drivers[driver.id] = driver

    for cluster in clusters:
        cluster_orders = [orders[oid] for oid in cluster.order_ids if oid in orders]
        if not cluster_orders:
            continue

        cluster_route = next(
            (
                r
                for r in routes.values()
                if r.cluster_id == cluster.id and r.driver_id == driver.id
            ),
            None,
        )

        # ── Pickup phase: driver → restaurant ────────────────────────────────
        first_order = cluster_orders[0]
        if first_order.restaurant_lat and first_order.restaurant_lon:
            pickup_waypoints = _interpolate_line(
                start_lat=driver.lat,
                start_lon=driver.lon,
                end_lat=first_order.restaurant_lat,
                end_lon=first_order.restaurant_lon,
                steps=8,
            )
            for i, (lat, lon) in enumerate(pickup_waypoints):
                progress = (i + 1) / len(pickup_waypoints) * 0.3
                await ws_manager.broadcast(
                    session,
                    DriverMovedEvent(
                        session_id=session,
                        data=DriverMovedEvent.Data(
                            driver_id=driver.id,
                            driver_name=driver.name,
                            lat=lat,
                            lon=lon,
                            progress_pct=progress,
                            current_order_id=first_order.id,
                            phase="pickup",
                            restaurant_name=first_order.restaurant_name,
                        ),
                    ),
                )
                driver.lat = lat
                driver.lon = lon
                state.drivers[driver.id] = driver
                await asyncio.sleep(0.15 / speed)

            pickup_time = _utc_now()
            for order in cluster_orders:
                order.pickup_at = pickup_time
                state.orders[order.id] = order

        # ── Delivery phase: restaurant → each customer ────────────────────────
        geojson_coords: List[Tuple[float, float]] = []
        if cluster_route and cluster_route.geojson:
            raw = cluster_route.geojson.get("geometry", {}).get("coordinates", [])
            geojson_coords = [(c[1], c[0]) for c in raw if len(c) >= 2]

        total_orders = len(cluster_orders)

        for order_idx, order in enumerate(cluster_orders):
            order.status = OrderStatus.IN_TRANSIT
            state.orders[order.id] = order

            await ws_manager.broadcast(
                session,
                OrderStatusChangedEvent(
                    session_id=session,
                    data=OrderStatusChangedEvent.Data(
                        order_id=order.id,
                        status="in_transit",
                        driver_id=driver.id,
                    ),
                ),
            )

            if geojson_coords and total_orders > 0:
                seg_start = int(len(geojson_coords) * order_idx / total_orders)
                seg_end = int(len(geojson_coords) * (order_idx + 1) / total_orders)
                seg_end = max(seg_end, seg_start + 2)
                segment = geojson_coords[seg_start:seg_end]
            else:
                segment = _interpolate_line(
                    start_lat=driver.lat,
                    start_lon=driver.lon,
                    end_lat=order.lat,
                    end_lon=order.lon,
                    steps=10,
                )

            steps = max(len(segment), 6)
            for step_i, (lat, lon) in enumerate(segment):
                overall_progress = 0.3 + 0.7 * (order_idx * steps + step_i) / (
                    total_orders * steps
                )
                await ws_manager.broadcast(
                    session,
                    DriverMovedEvent(
                        session_id=session,
                        data=DriverMovedEvent.Data(
                            driver_id=driver.id,
                            driver_name=driver.name,
                            lat=lat,
                            lon=lon,
                            progress_pct=round(overall_progress, 3),
                            current_order_id=order.id,
                            phase="delivery",
                            restaurant_name=order.restaurant_name,
                        ),
                    ),
                )
                driver.lat = lat
                driver.lon = lon
                state.drivers[driver.id] = driver
                await asyncio.sleep(0.12 / speed)

            # ── Mark delivered ────────────────────────────────────────────────
            delivered_time = _utc_now()
            order.status = OrderStatus.DELIVERED
            order.delivered_at = delivered_time
            state.orders[order.id] = order

            elapsed_minutes = (delivered_time - order.ordered_at).total_seconds() / 60

            route_distance = (
                cluster_route.total_distance_km / total_orders if cluster_route else 0.0
            )

            await ws_manager.broadcast(
                session,
                DeliveryCompletedEvent(
                    session_id=session,
                    data=DeliveryCompletedEvent.Data(
                        order_id=order.id,
                        driver_id=driver.id,
                        driver_name=driver.name,
                        restaurant_name=order.restaurant_name,
                        restaurant_zone=order.restaurant_zone,
                        customer_zone=order.zone,
                        time_taken_minutes=round(elapsed_minutes, 1),
                        distance_km=round(route_distance, 2),
                        ordered_at=order.ordered_at,
                        delivered_at=delivered_time,
                        algorithm=str(state.config.routing_method),
                    ),
                ),
            )

            delivery_records.append(
                DeliveryRecord(
                    order_id=order.id,
                    driver_name=driver.name,
                    restaurant_name=order.restaurant_name,
                    restaurant_zone=order.restaurant_zone,
                    customer_zone=order.zone,
                    ordered_at=order.ordered_at,
                    delivered_at=delivered_time,
                    duration_minutes=round(elapsed_minutes, 1),
                    distance_km=round(route_distance, 2),
                    algorithm=str(state.config.routing_method),
                    status="delivered",
                )
            )

            driver.deliveries_completed += 1
            state.drivers[driver.id] = driver

            state.metrics = order_completed(state.metrics)
            await _emit_metrics(session, state.metrics)
            await asyncio.sleep(0.1 / speed)

    # ── Driver finished all clusters ──────────────────────────────────────────
    driver.status = DriverStatus.COMPLETED
    state.drivers[driver.id] = driver

    logger.info(
        f"Driver {driver.name} finished — {driver.deliveries_completed} deliveries"
    )


def _interpolate_line(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    steps: int = 10,
) -> List[Tuple[float, float]]:
    return [
        (
            start_lat + (end_lat - start_lat) * i / max(steps - 1, 1),
            start_lon + (end_lon - start_lon) * i / max(steps - 1, 1),
        )
        for i in range(steps)
    ]