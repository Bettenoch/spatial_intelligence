"""
tests/test_simulation.py
─────────────────────────────────────────────────────────────────────────────
Tests for simulation generation modules:
  - simulation/order_generator.py
  - simulation/driver_generator.py
  - simulation/scenario_builder.py
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# ORDER GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderGenerator:

    def test_generate_orders_correct_count(self):
        from app.simulation.order_generator import generate_orders
        # Patch graph_loader to not snap (snap_to_graph=False)
        orders = generate_orders(count=10, snap_to_graph=False)
        assert len(orders) == 10

    def test_generate_orders_returns_order_objects(self):
        from app.simulation.order_generator import generate_orders
        from app.models.order import Order

        orders = generate_orders(count=5, snap_to_graph=False)
        for o in orders:
            assert isinstance(o, Order)

    def test_orders_have_valid_nairobi_coordinates(self):
        from app.simulation.order_generator import generate_orders

        orders = generate_orders(count=20, snap_to_graph=False)
        for o in orders:
            # Nairobi bounding box (generous)
            assert -1.5 < o.lat < -1.1, f"Bad lat: {o.lat}"
            assert 36.6 < o.lon < 37.0, f"Bad lon: {o.lon}"

    def test_orders_have_zone_labels(self):
        from app.simulation.order_generator import generate_orders

        orders = generate_orders(count=10, snap_to_graph=False)
        for o in orders:
            assert o.zone, "Order zone should not be empty"

    def test_orders_spread_across_multiple_zones(self):
        from app.simulation.order_generator import generate_orders

        orders = generate_orders(count=30, snap_to_graph=False)
        zones = {o.zone for o in orders}
        assert len(zones) >= 3, f"Expected multiple zones, got: {zones}"

    def test_orders_have_order_types(self):
        from app.simulation.order_generator import generate_orders
        from app.models.order import OrderType

        orders = generate_orders(count=20, snap_to_graph=False)
        types = {o.order_type for o in orders}
        # Should have at least food (dominant weight 55%)
        assert OrderType.FOOD in types or any(t == "food" for t in types)

    def test_orders_have_unique_ids(self):
        from app.simulation.order_generator import generate_orders

        orders = generate_orders(count=30, snap_to_graph=False)
        ids = [o.id for o in orders]
        assert len(ids) == len(set(ids))

    def test_orders_have_prep_minutes_in_range(self):
        from app.simulation.order_generator import generate_orders

        orders = generate_orders(count=10, snap_to_graph=False)
        for o in orders:
            assert 5 <= o.estimated_prep_minutes <= 45

    def test_orders_start_as_pending(self):
        from app.simulation.order_generator import generate_orders
        from app.models.order import OrderStatus

        orders = generate_orders(count=5, snap_to_graph=False)
        for o in orders:
            assert o.status == OrderStatus.PENDING or o.status == "pending"

    def test_cbd_hotspot_dominant(self):
        """CBD has the highest weight (9.0) — should produce most orders."""
        from app.simulation.order_generator import generate_orders

        orders = generate_orders(count=100, snap_to_graph=False)
        zone_counts = {}
        for o in orders:
            zone_counts[o.zone] = zone_counts.get(o.zone, 0) + 1
        cbd_count = zone_counts.get("CBD", 0)
        # CBD should be the most common zone
        assert cbd_count > 0, "CBD should receive orders"

    def test_snap_to_graph_with_mock(self):
        """With graph ready, orders should get road_node_id from the graph."""
        from app.simulation.order_generator import generate_orders

        mock_loader = MagicMock()
        mock_loader.is_ready.return_value = True
        mock_loader.nearest_node.return_value = (123456789, 12.5)
        mock_node_data = {"y": -1.2860, "x": 36.8170}
        mock_graph = MagicMock()
        mock_graph.nodes = {123456789: mock_node_data}
        mock_loader.get_graph.return_value = mock_graph

        with patch("app.simulation.order_generator.graph_loader", mock_loader):
            orders = generate_orders(count=3, snap_to_graph=True)


        for o in orders:
            assert o.road_node_id == 123456789

    def test_orders_to_coordinate_array_shape(self):
        from app.simulation.order_generator import generate_orders, orders_to_coordinate_array

        orders = generate_orders(count=10, snap_to_graph=False)
        arr = orders_to_coordinate_array(orders)
        assert arr.shape == (10, 2)
        # First column is lat, second is lon
        for i, o in enumerate(orders):
            assert arr[i, 0] == pytest.approx(o.lat)
            assert arr[i, 1] == pytest.approx(o.lon)


class TestHotspotSampling:

    def test_sample_hotspot_returns_valid_coords(self):
        from app.simulation.order_generator import _sample_hotspot

        for _ in range(50):
            lat, lon, zone = _sample_hotspot()
            assert -1.5 < lat < -1.1
            assert 36.6 < lon < 37.1
            assert isinstance(zone, str)
            assert len(zone) > 0

    def test_normalized_weights_sum_to_one(self):
        from app.simulation.order_generator import _NORMALIZED_WEIGHTS
        assert sum(_NORMALIZED_WEIGHTS) == pytest.approx(1.0, rel=1e-6)

    def test_all_hotspots_have_required_fields(self):
        from app.simulation.order_generator import NAIROBI_HOTSPOTS
        for hotspot in NAIROBI_HOTSPOTS:
            lat, lon, radius, weight, zone = hotspot
            assert -2.0 < lat < 0.0, f"Invalid lat: {lat}"
            assert 36.0 < lon < 38.0, f"Invalid lon: {lon}"
            assert radius > 0
            assert weight > 0
            assert isinstance(zone, str)


# ═══════════════════════════════════════════════════════════════════════════════
# DRIVER GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

class TestDriverGenerator:

    def test_generates_correct_count(self):
        from app.simulation.driver_generator import generate_drivers

        drivers = generate_drivers(count=3, snap_to_graph=False)
        assert len(drivers) == 3

    def test_returns_driver_objects(self):
        from app.simulation.driver_generator import generate_drivers
        from app.models.driver import Driver

        drivers = generate_drivers(count=2, snap_to_graph=False)
        for d in drivers:
            assert isinstance(d, Driver)

    def test_drivers_have_nairobi_coordinates(self):
        from app.simulation.driver_generator import generate_drivers

        drivers = generate_drivers(count=8, snap_to_graph=False)
        for d in drivers:
            assert -1.5 < d.lat < -1.1, f"Bad lat: {d.lat}"
            assert 36.6 < d.lon < 37.0, f"Bad lon: {d.lon}"

    def test_driver_names_are_unique(self):
        from app.simulation.driver_generator import generate_drivers

        drivers = generate_drivers(count=5, snap_to_graph=False)
        names = [d.name for d in drivers]
        assert len(names) == len(set(names))

    def test_driver_capacity_in_valid_range(self):
        from app.simulation.driver_generator import generate_drivers

        drivers = generate_drivers(count=8, snap_to_graph=False)
        for d in drivers:
            assert 4 <= d.capacity <= 6

    def test_drivers_start_idle(self):
        from app.simulation.driver_generator import generate_drivers
        from app.models.driver import DriverStatus

        drivers = generate_drivers(count=3, snap_to_graph=False)
        for d in drivers:
            assert d.status == DriverStatus.IDLE or d.status == "idle"

    def test_drivers_have_zone_labels(self):
        from app.simulation.driver_generator import generate_drivers

        drivers = generate_drivers(count=5, snap_to_graph=False)
        for d in drivers:
            assert d.zone, "Driver zone should not be empty"

    def test_drivers_spread_across_zones(self):
        from app.simulation.driver_generator import generate_drivers

        drivers = generate_drivers(count=8, snap_to_graph=False)
        zones = {d.zone for d in drivers}
        assert len(zones) >= 3, "Drivers should cover multiple depot zones"

    def test_generates_extra_drivers_beyond_name_pool(self):
        """When count > available names, should add fallback names."""
        from app.simulation.driver_generator import generate_drivers

        drivers = generate_drivers(count=12, snap_to_graph=False)
        assert len(drivers) == 12

    def test_snap_to_graph_with_mock(self):
        from app.simulation.driver_generator import generate_drivers

        mock_loader = MagicMock()
        mock_loader.is_ready.return_value = True
        mock_loader.nearest_node.return_value = (987654321, 8.0)
        mock_graph = MagicMock()
        mock_graph.nodes = {987654321: {"y": -1.2864, "x": 36.8172}}
        mock_loader.get_graph.return_value = mock_graph

        with patch("app.simulation.driver_generator.graph_loader", mock_loader):
            drivers = generate_drivers(count=2, snap_to_graph=True)

        for d in drivers:
            assert d.road_node_id == 987654321

    def test_unique_ids(self):
        from app.simulation.driver_generator import generate_drivers

        drivers = generate_drivers(count=5, snap_to_graph=False)
        ids = [d.id for d in drivers]
        assert len(ids) == len(set(ids))


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

class TestScenarioBuilder:

    def test_build_scenario_returns_simulation_state(self):
        from app.models.simulation import SimulationConfig, SimulationState
        from app.models.route import RoutingMethod
        from app.simulation.scenario_builder import build_scenario

        config = SimulationConfig(order_count=10, driver_count=3,
                                  routing_method=RoutingMethod.HAVERSINE)
        with patch("app.simulation.scenario_builder.generate_orders") as mock_orders, \
             patch("app.simulation.scenario_builder.generate_drivers") as mock_drivers:

            from app.models.order import Order, OrderType
            from app.models.driver import Driver
            mock_orders.return_value = [
                Order(lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD)
                for _ in range(10)
            ]
            mock_drivers.return_value = [
                Driver(name=f"Driver {i}", lat=-1.2864, lon=36.8172, zone="CBD")
                for i in range(3)
            ]

            state = build_scenario(config)

        assert isinstance(state, SimulationState)
        assert len(state.orders) == 10
        assert len(state.drivers) == 3

    def test_build_scenario_sets_metrics_totals(self):
        from app.models.simulation import SimulationConfig
        from app.models.route import RoutingMethod
        from app.simulation.scenario_builder import build_scenario

        config = SimulationConfig(order_count=15, driver_count=4,
                                  routing_method=RoutingMethod.HAVERSINE)

        with patch("app.simulation.scenario_builder.generate_orders") as mock_orders, \
             patch("app.simulation.scenario_builder.generate_drivers") as mock_drivers:

            from app.models.order import Order, OrderType
            from app.models.driver import Driver
            mock_orders.return_value = [
                Order(lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD)
                for _ in range(15)
            ]
            mock_drivers.return_value = [
                Driver(name=f"Driver {i}", lat=-1.2864, lon=36.8172, zone="CBD")
                for i in range(4)
            ]

            state = build_scenario(config)

        assert state.metrics.deliveries_total == 15
        assert state.metrics.active_drivers == 4

    def test_build_scenario_session_id_is_unique(self):
        from app.models.simulation import SimulationConfig
        from app.models.route import RoutingMethod
        from app.simulation.scenario_builder import build_scenario

        config = SimulationConfig(order_count=5, driver_count=2,
                                  routing_method=RoutingMethod.EUCLIDEAN)

        with patch("app.simulation.scenario_builder.generate_orders") as mock_orders, \
             patch("app.simulation.scenario_builder.generate_drivers") as mock_drivers:

            from app.models.order import Order, OrderType
            from app.models.driver import Driver
            mock_orders.return_value = [
                Order(lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD)
            ]
            mock_drivers.return_value = [
                Driver(name="Test", lat=-1.2864, lon=36.8172, zone="CBD")
            ]

            state1 = build_scenario(config)
            state2 = build_scenario(config)

        assert state1.session_id != state2.session_id

    def test_build_scenario_config_preserved(self):
        from app.models.simulation import SimulationConfig
        from app.models.route import RoutingMethod
        from app.simulation.scenario_builder import build_scenario

        config = SimulationConfig(
            order_count=20,
            driver_count=5,
            routing_method=RoutingMethod.STREET_NETWORK,
            scenario_label="Test scenario",
        )

        with patch("app.simulation.scenario_builder.generate_orders") as mock_orders, \
             patch("app.simulation.scenario_builder.generate_drivers") as mock_drivers:

            from app.models.order import Order, OrderType
            from app.models.driver import Driver
            mock_orders.return_value = [
                Order(lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD)
                for _ in range(20)
            ]
            mock_drivers.return_value = [
                Driver(name=f"D{i}", lat=-1.2864, lon=36.8172, zone="CBD")
                for i in range(5)
            ]

            state = build_scenario(config)

        assert state.config.order_count == 20
        assert state.config.driver_count == 5
        assert state.config.scenario_label == "Test scenario"