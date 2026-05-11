"""
tests/test_services.py
─────────────────────────────────────────────────────────────────────────────
Tests for the service layer:
  - services/metrics_service.py
  - services/routing_service.py
  - services/education_service.py
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.cluster import Cluster
from app.models.driver import Driver, DriverStatus
from app.models.order import Order, OrderType, OrderStatus
from app.models.route import Route, RoutingMethod, RouteWaypoint
from app.models.simulation import SimulationMetrics
from app.services.metrics_service import compute_metrics


# ═══════════════════════════════════════════════════════════════════════════════
# METRICS SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetricsService:

    def test_naive_distance_calculation(self):
        from app.services.metrics_service import calculate_naive_distance

        result = calculate_naive_distance(order_count=10, avg_delivery_distance_km=3.5)
        # 10 orders × 3.5km × 2 (round trip) = 70km
        assert result == pytest.approx(70.0)

    def test_naive_distance_zero_orders(self):
        from app.services.metrics_service import calculate_naive_distance
        assert calculate_naive_distance(0) == pytest.approx(0.0)

    def test_compute_metrics_with_routes(self):
        from app.services.metrics_service import compute_metrics

        routes = {
            "r1": Route(
                id="r1", cluster_id="c1", driver_id="d1",
                method=RoutingMethod.HAVERSINE,
                total_distance_km=5.0,
                naive_distance_km=14.0,
            ),
            "r2": Route(
                id="r2", cluster_id="c2", driver_id="d2",
                method=RoutingMethod.HAVERSINE,
                total_distance_km=3.5,
                naive_distance_km=10.0,
            ),
        }
        existing = SimulationMetrics(deliveries_completed=5, deliveries_total=20)
        result = compute_metrics(routes, order_count=20, existing_metrics=existing)

        assert result.optimised_distance_km == pytest.approx(8.5)
        assert result.naive_distance_km == pytest.approx(24.0)
        assert result.distance_saved_km == pytest.approx(15.5)
        assert result.deliveries_completed == 5  # preserved from existing

    def test_compute_metrics_no_routes_uses_estimate(self):
        from app.services.metrics_service import compute_metrics

        result = compute_metrics({}, order_count=10, existing_metrics=SimulationMetrics())
        # Should use estimate when no route naive distances available
        assert result.naive_distance_km == pytest.approx(70.0)  # 10 * 3.5 * 2

    def test_fuel_saved_litres_computed(self):
        from app.services.metrics_service import compute_metrics

        routes = {"r1": Route(
            id="r1", cluster_id="c1", driver_id="d1",
            method=RoutingMethod.HAVERSINE,
            total_distance_km=50.0,
            naive_distance_km=100.0,
        )}
        result = compute_metrics(routes, order_count=10, existing_metrics=SimulationMetrics())
        # 50km saved, 10L/100km → 5L saved
        assert result.fuel_saved_litres == pytest.approx(5.0)

    def test_cost_saved_kes_computed(self):
        from app.services.metrics_service import compute_metrics
        from app.core.config import settings

        routes = {"r1": Route(
            id="r1", cluster_id="c1", driver_id="d1",
            method=RoutingMethod.HAVERSINE,
            total_distance_km=50.0,
            naive_distance_km=100.0,
        )}
        result = compute_metrics(routes, order_count=10, existing_metrics=SimulationMetrics())
        expected_cost = 5.0 * settings.fuel_price_kes_per_litre
        assert result.cost_saved_kes == pytest.approx(expected_cost, rel=0.01)

    def test_co2_saved_computed(self):
        from app.services.metrics_service import compute_metrics
        from app.core.config import settings

        routes = {"r1": Route(
            id="r1", cluster_id="c1", driver_id="d1",
            method=RoutingMethod.HAVERSINE,
            total_distance_km=50.0,
            naive_distance_km=100.0,
        )}
        result = compute_metrics(routes, order_count=10, existing_metrics=SimulationMetrics())
        expected_co2 = 5.0 * settings.co2_kg_per_litre
        assert result.co2_saved_kg == pytest.approx(expected_co2, rel=0.01)

    def test_time_saved_minutes_computed(self):
        from app.services.metrics_service import compute_metrics

        routes = {"r1": Route(
            id="r1", cluster_id="c1", driver_id="d1",
            method=RoutingMethod.HAVERSINE,
            total_distance_km=0.0,
            naive_distance_km=60.0,  # 60km saved at 30km/h = 120 minutes
        )}
        result = compute_metrics(routes, order_count=5, existing_metrics=SimulationMetrics())
        assert result.time_saved_minutes == pytest.approx(120.0, rel=0.01)

    def test_savings_percentage_property(self):
        metrics = SimulationMetrics(
            naive_distance_km=100.0,
            distance_saved_km=40.0,
        )
        assert metrics.savings_percentage == pytest.approx(40.0)

    def test_savings_percentage_zero_naive(self):
        metrics = SimulationMetrics(naive_distance_km=0.0, distance_saved_km=0.0)
        assert metrics.savings_percentage == 0.0

    def test_savings_percentage_non_negative(self):
        routes = {"r1": Route(
            id="r1", cluster_id="c1", driver_id="d1",
            method=RoutingMethod.HAVERSINE,
            total_distance_km=200.0,  # optimised > naive (edge case)
            naive_distance_km=50.0,
        )}
        result = compute_metrics(routes, order_count=10, existing_metrics=SimulationMetrics())
        assert result.distance_saved_km >= 0.0

    def test_order_completed_increments_counter(self):
        from app.services.metrics_service import order_completed

        metrics = SimulationMetrics(deliveries_completed=5)
        updated = order_completed(metrics)
        assert updated.deliveries_completed == 6
        # Original unchanged
        assert metrics.deliveries_completed == 5

    def test_order_completed_preserves_other_fields(self):
        from app.services.metrics_service import order_completed

        metrics = SimulationMetrics(
            deliveries_completed=3,
            optimised_distance_km=45.2,
            fuel_saved_litres=2.1,
        )
        updated = order_completed(metrics)
        assert updated.optimised_distance_km == 45.2
        assert updated.fuel_saved_litres == 2.1


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTING SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoutingService:

    def make_cluster_driver_orders(self):
        orders = [
            Order(lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD),
            Order(lat=-1.2870, lon=36.8180, zone="CBD", order_type=OrderType.FOOD),
            Order(lat=-1.2855, lon=36.8165, zone="CBD", order_type=OrderType.FOOD),
        ]
        cluster = Cluster(
            order_ids=[o.id for o in orders],
            centroid_lat=-1.2863,
            centroid_lon=36.8172,
            zone_label="CBD cluster",
        )
        driver = Driver(name="Brian K.", lat=-1.2900, lon=36.8200, zone="CBD")
        orders_dict = {o.id: o for o in orders}
        return cluster, driver, orders_dict

    @pytest.mark.asyncio
    async def test_euclidean_route_returns_route_object(self):
        from app.services.routing_service import compute_route

        cluster, driver, orders = self.make_cluster_driver_orders()
        route = await compute_route(cluster, driver, orders, RoutingMethod.EUCLIDEAN)

        assert isinstance(route, Route)
        assert route.method == RoutingMethod.EUCLIDEAN or route.method == "euclidean"

    @pytest.mark.asyncio
    async def test_haversine_route_returns_route_object(self):
        from app.services.routing_service import compute_route

        cluster, driver, orders = self.make_cluster_driver_orders()
        route = await compute_route(cluster, driver, orders, RoutingMethod.HAVERSINE)

        assert isinstance(route, Route)
        assert route.total_distance_km > 0
        assert route.estimated_duration_minutes > 0

    @pytest.mark.asyncio
    async def test_euclidean_route_has_geojson(self):
        from app.services.routing_service import compute_route

        cluster, driver, orders = self.make_cluster_driver_orders()
        route = await compute_route(cluster, driver, orders, RoutingMethod.EUCLIDEAN)

        assert route.geojson is not None
        assert route.geojson["type"] == "Feature"
        assert route.geojson["geometry"]["type"] == "LineString"

    @pytest.mark.asyncio
    async def test_haversine_route_has_waypoints(self):
        from app.services.routing_service import compute_route

        cluster, driver, orders = self.make_cluster_driver_orders()
        route = await compute_route(cluster, driver, orders, RoutingMethod.HAVERSINE)

        assert len(route.waypoints) > 0

    @pytest.mark.asyncio
    async def test_route_cluster_and_driver_ids_correct(self):
        from app.services.routing_service import compute_route

        cluster, driver, orders = self.make_cluster_driver_orders()
        route = await compute_route(cluster, driver, orders, RoutingMethod.EUCLIDEAN)

        assert route.cluster_id == cluster.id
        assert route.driver_id == driver.id

    @pytest.mark.asyncio
    async def test_naive_distance_greater_than_optimised(self):
        """Naive (separate round-trips) should be more than optimised (single shared trip)."""
        from app.services.routing_service import compute_route

        cluster, driver, orders = self.make_cluster_driver_orders()
        route = await compute_route(cluster, driver, orders, RoutingMethod.HAVERSINE)

        assert route.naive_distance_km > route.total_distance_km

    @pytest.mark.asyncio
    async def test_empty_cluster_returns_empty_route(self):
        from app.services.routing_service import compute_route

        cluster = Cluster(order_ids=[], centroid_lat=-1.2864, centroid_lon=36.8172)
        driver = Driver(name="Test", lat=-1.2864, lon=36.8172, zone="CBD")
        route = await compute_route(cluster, driver, {}, RoutingMethod.EUCLIDEAN)

        assert route.total_distance_km == 0.0

    @pytest.mark.asyncio
    async def test_unsupported_method_raises_error(self):
        from app.services.routing_service import compute_route
        from app.core.exceptions import UnsupportedRoutingMethod

        cluster, driver, orders = self.make_cluster_driver_orders()
        with pytest.raises((UnsupportedRoutingMethod, ValueError)):
            await compute_route(cluster, driver, orders, "invalid_method")  # type: ignore

    @pytest.mark.asyncio
    async def test_street_network_falls_back_to_haversine_on_osrm_failure(self):
        """When OSRM is down, street_network routing should still return a route."""
        from app.services.routing_service import compute_route
        from app.core.exceptions import OSRMConnectionError

        cluster, driver, orders = self.make_cluster_driver_orders()

        with patch("app.services.routing_service.osrm_client") as mock_osrm:
            mock_osrm.get_route_geometry_and_distance = AsyncMock(
                side_effect=OSRMConnectionError("http://test")
            )
            # The OSRM client internally falls back to haversine
            # So we test that compute_route itself produces a valid route
            route = await compute_route(cluster, driver, orders, RoutingMethod.STREET_NETWORK)

        assert isinstance(route, Route)

    def test_naive_distance_helper(self):
        from app.services.routing_service import _naive_distance
        from app.algorithms.distance.haversine import haversine_distance

        driver = Driver(name="Test", lat=-1.2864, lon=36.8172, zone="CBD")
        orders = [
            Order(lat=-1.2870, lon=36.8180, zone="CBD", order_type=OrderType.FOOD),
            Order(lat=-1.2855, lon=36.8165, zone="CBD", order_type=OrderType.FOOD),
        ]

        result = _naive_distance(driver, orders)
        expected = sum(
            haversine_distance(driver.lat, driver.lon, o.lat, o.lon) * 2
            for o in orders
        )
        assert result == pytest.approx(expected)

    def test_estimate_duration(self):
        from app.services.routing_service import _estimate_duration

        # 30km at 25 km/h = 72 minutes
        assert _estimate_duration(30.0, avg_speed_kmh=25.0) == pytest.approx(72.0)

    def test_build_waypoints_structure(self):
        import numpy as np
        from app.services.routing_service import _build_waypoints

        orders = [
            Order(lat=-1.2870, lon=36.8180, zone="CBD", order_type=OrderType.FOOD),
            Order(lat=-1.2855, lon=36.8165, zone="CBD", order_type=OrderType.FOOD),
        ]
        # coords: [driver, order0, order1]
        coords = np.array([[-1.2900, 36.8200], [-1.2870, 36.8180], [-1.2855, 36.8165]])
        tour = [0, 1, 2]  # driver → order0 → order1

        waypoints = _build_waypoints(coords, tour, orders)

        assert len(waypoints) == 3
        assert waypoints[0].order_id is None  # driver position
        assert waypoints[1].order_id == orders[0].id
        assert waypoints[2].order_id == orders[1].id
        assert waypoints[0].sequence == 0
        assert waypoints[1].sequence == 1


# ═══════════════════════════════════════════════════════════════════════════════
# EDUCATION SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class TestEducationService:

    def test_get_all_algorithms_returns_list(self):
        from app.services.education_service import get_all_algorithms
        result = get_all_algorithms()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_all_algorithms_have_required_fields(self):
        from app.services.education_service import get_all_algorithms
        for algo in get_all_algorithms():
            assert "id" in algo
            assert "name" in algo
            assert "category" in algo

    def test_get_algorithm_by_known_id(self):
        from app.services.education_service import get_algorithm

        for algo_id in ["euclidean", "haversine", "dbscan", "kmeans", "dijkstra", "vrp"]:
            result = get_algorithm(algo_id)
            assert result is not None, f"Algorithm '{algo_id}' not found"
            assert result["id"] == algo_id

    def test_get_algorithm_unknown_id_returns_none(self):
        from app.services.education_service import get_algorithm
        assert get_algorithm("nonexistent_algo") is None

    def test_get_concept_by_known_id(self):
        from app.services.education_service import get_concept

        for concept_id in ["clustering", "gis", "road_network_graph"]:
            result = get_concept(concept_id)
            assert result is not None, f"Concept '{concept_id}' not found"
            assert result["id"] == concept_id

    def test_get_concept_unknown_id_returns_none(self):
        from app.services.education_service import get_concept
        assert get_concept("nonexistent_concept") is None

    def test_algorithm_content_has_formula(self):
        from app.services.education_service import get_algorithm
        for algo_id in ["euclidean", "haversine", "dbscan"]:
            result = get_algorithm(algo_id)
            assert "formula" in result, f"Algorithm '{algo_id}' missing formula"

    def test_algorithm_content_has_pros_cons(self):
        from app.services.education_service import get_algorithm
        result = get_algorithm("dbscan")
        assert "pros" in result
        assert "cons" in result
        assert isinstance(result["pros"], list)
        assert len(result["pros"]) > 0

    def test_algorithm_content_has_nairobi_context(self):
        from app.services.education_service import get_algorithm
        for algo_id in ["euclidean", "haversine", "dbscan"]:
            result = get_algorithm(algo_id)
            assert "nairobi_context" in result

    def test_caching_returns_same_content(self):
        from app.services.education_service import get_all_algorithms
        result1 = get_all_algorithms()
        result2 = get_all_algorithms()
        assert result1 == result2

    def test_content_file_missing_returns_empty_gracefully(self):
        """If the JSON file is missing, service should return empty lists."""
        from app.services import education_service

        original_cache = education_service._cache
        education_service._cache = None

        with patch.object(education_service, "_CONTENT_PATH",
                          Path("/nonexistent/path.json")):
            result = education_service.get_all_algorithms()

        # Restore
        education_service._cache = original_cache
        assert isinstance(result, list)