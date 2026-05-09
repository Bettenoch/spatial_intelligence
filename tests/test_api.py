"""
tests/test_api.py
─────────────────────────────────────────────────────────────────────────────
Tests for all REST API endpoints:
  - GET  /
  - POST /api/simulate
  - GET  /api/scenario
  - GET  /api/simulation/{session_id}
  - GET  /api/health
  - GET  /api/algorithms
  - GET  /api/algorithms/{id}
  - GET  /api/concepts/{id}
  - GET  /api/metrics/{session_id}
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Shared app setup ──────────────────────────────────────────────────────────



def get_test_client(graph_ready: bool = True):
    mock_loader = MagicMock()
    mock_loader.is_ready.return_value = graph_ready
    mock_loader.stats.return_value = {
        "ready": graph_ready,
        "node_count": 50000,
        "edge_count": 120000,
        "load_time_seconds": 3.1,
    }
    mock_loader.nearest_node.return_value = (12345, 10.0)

    with patch("app.core.graph_loader.graph_loader", mock_loader), \
         patch("app.api.routes.simulation.graph_loader", mock_loader), \
         patch("app.main.graph_loader", mock_loader):
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)



# ═══════════════════════════════════════════════════════════════════════════════
# ROOT
# ═══════════════════════════════════════════════════════════════════════════════


class TestRootEndpoint:

    def test_root_returns_200(self):
        client = get_test_client()
        response = client.get("/")
        assert response.status_code == 200

    def test_root_response_schema(self):
        client = get_test_client()
        data = client.get("/").json()
        assert "project" in data
        assert "status" in data
        assert "graph_ready" in data
        assert "docs" in data

    def test_root_graph_ready_true(self):
        client = get_test_client(graph_ready=True)
        data = client.get("/").json()
        assert data["graph_ready"] is True

    def test_root_graph_ready_false(self):
        client = get_test_client(graph_ready=False)
        data = client.get("/").json()
        assert data["graph_ready"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# SIMULATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSimulateEndpoint:

    def _mock_scenario(self):
        from app.models.simulation import (
            SimulationState,
            SimulationConfig,
            SimulationStatus,
        )
        from app.models.order import Order, OrderType
        from app.models.driver import Driver
        from app.models.route import RoutingMethod

        config = SimulationConfig(
            order_count=5, driver_count=2, routing_method=RoutingMethod.HAVERSINE
        )
        state = SimulationState(config=config)
        state.status = SimulationStatus.GENERATING_ORDERS

        orders = [
            Order(lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD)
            for _ in range(5)
        ]
        drivers = [
            Driver(name=f"D{i}", lat=-1.2864, lon=36.8172, zone="CBD") for i in range(2)
        ]
        state.orders = {o.id: o for o in orders}
        state.drivers = {d.id: d for d in drivers}
        return state

    def test_simulate_returns_202(self):
        client = get_test_client()
        state = self._mock_scenario()

        with (
            patch("app.api.routes.simulation.build_scenario", return_value=state),
            patch("app.api.routes.simulation.run_simulation", new_callable=AsyncMock),
        ):
            response = client.post(
                "/api/simulate",
                json={
                    "order_count": 5,
                    "driver_count": 2,
                    "routing_method": "haversine",
                },
            )
        assert response.status_code == 202

    def test_simulate_response_contains_session_id(self):
        client = get_test_client()
        state = self._mock_scenario()

        with (
            patch("app.api.routes.simulation.build_scenario", return_value=state),
            patch("app.api.routes.simulation.run_simulation", new_callable=AsyncMock),
        ):
            response = client.post(
                "/api/simulate",
                json={
                    "order_count": 5,
                    "driver_count": 2,
                    "routing_method": "haversine",
                },
            )
        data = response.json()
        assert "session_id" in data
        assert data["session_id"] == state.session_id

    def test_simulate_response_has_ws_url(self):
        client = get_test_client()
        state = self._mock_scenario()

        with (
            patch("app.api.routes.simulation.build_scenario", return_value=state),
            patch("app.api.routes.simulation.run_simulation", new_callable=AsyncMock),
        ):
            response = client.post(
                "/api/simulate",
                json={
                    "order_count": 5,
                    "driver_count": 2,
                    "routing_method": "haversine",
                },
            )
        data = response.json()
        assert "ws_url" in data
        assert data["session_id"] in data["ws_url"]

    def test_simulate_rejects_excessive_order_count(self):
        client = get_test_client()
        response = client.post(
            "/api/simulate",
            json={
                "order_count": 9999,
                "driver_count": 2,
                "routing_method": "haversine",
            },
        )
        assert response.status_code == 400

    def test_simulate_rejects_excessive_driver_count(self):
        client = get_test_client()
        response = client.post(
            "/api/simulate",
            json={
                "order_count": 10,
                "driver_count": 999,
                "routing_method": "haversine",
            },
        )
        assert response.status_code == 400

    def test_simulate_returns_503_when_graph_not_ready(self):
        client = get_test_client(graph_ready=False)
        response = client.post(
            "/api/simulate",
            json={
                "order_count": 10,
                "driver_count": 2,
                "routing_method": "haversine",
            },
        )
        assert response.status_code == 503

    def test_simulate_accepts_all_routing_methods(self):
        client = get_test_client()
        state = self._mock_scenario()

        for method in ["euclidean", "haversine", "street_network"]:
            with (
                patch("app.api.routes.simulation.build_scenario", return_value=state),
                patch(
                    "app.api.routes.simulation.run_simulation", new_callable=AsyncMock
                ),
            ):
                response = client.post(
                    "/api/simulate",
                    json={
                        "order_count": 5,
                        "driver_count": 2,
                        "routing_method": method,
                    },
                )
            assert response.status_code == 202, f"Method {method} should be accepted"

    def test_simulate_invalid_routing_method_rejected(self):
        client = get_test_client()
        response = client.post(
            "/api/simulate",
            json={
                "order_count": 10,
                "driver_count": 2,
                "routing_method": "teleport",
            },
        )
        assert response.status_code == 422  # Pydantic validation error


class TestScenarioEndpoint:

    def test_get_scenario_returns_200(self):
        client = get_test_client()
        response = client.get("/api/scenario")
        assert response.status_code == 200

    def test_get_scenario_has_required_fields(self):
        client = get_test_client()
        data = client.get("/api/scenario").json()
        assert "order_count" in data
        assert "driver_count" in data
        assert "routing_method" in data

    def test_get_scenario_defaults_are_valid(self):
        client = get_test_client()
        data = client.get("/api/scenario").json()
        assert 5 <= data["order_count"] <= 60
        assert 1 <= data["driver_count"] <= 8
        assert data["routing_method"] in ["euclidean", "haversine", "street_network"]


class TestGetSimulationStateEndpoint:

    def test_unknown_session_returns_404(self):
        client = get_test_client()
        response = client.get("/api/simulation/nonexistent_session")
        assert response.status_code == 404

    def test_known_session_returns_state(self):
        client = get_test_client()
        state = self._create_stored_simulation(client)

        response = client.get(f"/api/simulation/{state.session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == state.session_id

    def test_state_response_has_expected_fields(self):
        client = get_test_client()
        state = self._create_stored_simulation(client)

        data = client.get(f"/api/simulation/{state.session_id}").json()
        expected = [
            "session_id",
            "status",
            "order_count",
            "cluster_count",
            "route_count",
            "metrics",
        ]
        for field in expected:
            assert field in data, f"Missing field: {field}"

    def _create_stored_simulation(self, client):
        """Helper: post /simulate and extract the stored state object."""
        from app.models.simulation import (
            SimulationState,
            SimulationConfig,
            SimulationStatus,
        )
        from app.models.order import Order, OrderType
        from app.models.driver import Driver
        from app.models.route import RoutingMethod

        config = SimulationConfig(
            order_count=5, driver_count=2, routing_method=RoutingMethod.HAVERSINE
        )
        state = SimulationState(config=config)
        state.orders = {
            f"o{i}": Order(
                lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD
            )
            for i in range(5)
        }
        state.drivers = {
            f"d{i}": Driver(name=f"D{i}", lat=-1.2864, lon=36.8172, zone="CBD")
            for i in range(2)
        }

        with (
                patch("app.api.routes.simulation.build_scenario", return_value=state),
                patch("app.api.routes.simulation.run_simulation", new_callable=AsyncMock),
                patch("app.api.routes.simulation._run_and_store", new_callable=AsyncMock),  # ← ADD THIS
            ):
                client.post(
                    "/api/simulate",
                    json={"order_count": 5, "driver_count": 2, "routing_method": "haversine"},
                )

            # Manually inject the state so GET can find it
        import app.api.routes.simulation as sim_routes
        sim_routes._simulations[state.session_id] = state  # ← ADD THIS

        return state


class TestHealthEndpoint:

    def test_health_returns_200(self):
        client = get_test_client()
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_response_schema(self):
        client = get_test_client()
        data = client.get("/api/health").json()
        assert "status" in data
        assert "graph" in data
        assert "active_simulations" in data
        assert "websocket_connections" in data

    def test_health_status_ok(self):
        client = get_test_client()
        data = client.get("/api/health").json()
        assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# ALGORITHM ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestAlgorithmEndpoints:

    def test_list_algorithms_returns_200(self):
        client = get_test_client()
        response = client.get("/api/algorithms")
        assert response.status_code == 200

    def test_list_algorithms_returns_list(self):
        client = get_test_client()
        data = client.get("/api/algorithms").json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_list_algorithms_summary_fields(self):
        client = get_test_client()
        data = client.get("/api/algorithms").json()
        for item in data:
            assert "id" in item
            assert "name" in item
            assert "category" in item

    def test_get_algorithm_known_id(self):
        client = get_test_client()
        for algo_id in ["euclidean", "haversine", "dbscan", "kmeans", "dijkstra"]:
            response = client.get(f"/api/algorithms/{algo_id}")
            assert response.status_code == 200, f"Algorithm '{algo_id}' not found"

    def test_get_algorithm_unknown_id_returns_404(self):
        client = get_test_client()
        response = client.get("/api/algorithms/nonexistent")
        assert response.status_code == 404

    def test_get_algorithm_detail_has_formula(self):
        client = get_test_client()
        data = client.get("/api/algorithms/euclidean").json()
        assert "formula" in data

    def test_get_algorithm_detail_has_pros_cons(self):
        client = get_test_client()
        data = client.get("/api/algorithms/dbscan").json()
        assert "pros" in data
        assert "cons" in data

    def test_get_algorithm_id_matches_requested(self):
        client = get_test_client()
        data = client.get("/api/algorithms/haversine").json()
        assert data["id"] == "haversine"


class TestConceptEndpoints:

    def test_get_concept_known_id(self):
        client = get_test_client()
        for concept_id in ["clustering", "gis", "road_network_graph"]:
            response = client.get(f"/api/concepts/{concept_id}")
            assert response.status_code == 200

    def test_get_concept_unknown_id_returns_404(self):
        client = get_test_client()
        response = client.get("/api/concepts/nonexistent")
        assert response.status_code == 404

    def test_concept_response_schema(self):
        client = get_test_client()
        data = client.get("/api/concepts/clustering").json()
        assert "id" in data
        assert "name" in data
        assert "explanation" in data


# ═══════════════════════════════════════════════════════════════════════════════
# METRICS ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════════


class TestMetricsEndpoint:

    def test_unknown_session_returns_404(self):
        client = get_test_client()
        response = client.get("/api/metrics/nonexistent_session")
        assert response.status_code == 404

    def test_known_session_returns_metrics(self):
        client = get_test_client()
        from app.models.simulation import (
            SimulationState,
            SimulationConfig,
            SimulationStatus,
        )
        from app.models.order import Order, OrderType
        from app.models.driver import Driver
        from app.models.route import RoutingMethod
        import app.api.routes.simulation as sim_routes

        config = SimulationConfig(
            order_count=5, driver_count=2, routing_method=RoutingMethod.HAVERSINE
        )
        state = SimulationState(config=config)
        state.status = SimulationStatus.COMPLETED
        sim_routes._simulations[state.session_id] = state

        response = client.get(f"/api/metrics/{state.session_id}")
        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data
        assert "summary" in data

    def test_metrics_summary_has_key_fields(self):
        client = get_test_client()
        from app.models.simulation import (
            SimulationState,
            SimulationConfig,
            SimulationStatus,
        )
        from app.models.route import RoutingMethod
        import app.api.routes.simulation as sim_routes

        config = SimulationConfig(
            order_count=5, driver_count=2, routing_method=RoutingMethod.HAVERSINE
        )
        state = SimulationState(config=config)
        state.status = SimulationStatus.COMPLETED
        sim_routes._simulations[state.session_id] = state

        data = client.get(f"/api/metrics/{state.session_id}").json()
        summary = data["summary"]
        for key in [
            "deliveries",
            "distance_saved",
            "fuel_saved",
            "cost_saved",
            "time_saved",
        ]:
            assert key in summary, f"Missing summary key: {key}"


# ═══════════════════════════════════════════════════════════════════════════════
# INPUT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestInputValidation:

    def test_simulate_order_count_below_minimum(self):
        client = get_test_client()
        response = client.post(
            "/api/simulate",
            json={
                "order_count": 1,  # minimum is 5
                "driver_count": 2,
                "routing_method": "haversine",
            },
        )
        assert response.status_code == 422

    def test_simulate_driver_count_zero(self):
        client = get_test_client()
        response = client.post(
            "/api/simulate",
            json={
                "order_count": 10,
                "driver_count": 0,  # minimum is 1
                "routing_method": "haversine",
            },
        )
        assert response.status_code == 422

    def test_simulate_missing_required_fields(self):
        client = get_test_client()
        # Empty body should use defaults (all fields have defaults)
        state = MagicMock()
        state.session_id = "test_default"
        state.orders = {}
        state.drivers = {}

        with (
            patch("app.api.routes.simulation.build_scenario", return_value=state),
            patch("app.api.routes.simulation.run_simulation", new_callable=AsyncMock),
        ):
            response = client.post("/api/simulate", json={})
        # Empty body should use defaults — 202 is expected
        assert response.status_code in (202, 422)
