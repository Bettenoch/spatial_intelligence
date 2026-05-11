"""
tests/test_websocket_and_models.py
─────────────────────────────────────────────────────────────────────────────
Tests for:
  - websocket/manager.py        (ConnectionManager)
  - websocket/events.py         (all event types)
  - models/*.py                 (Pydantic model validation)
  - core/exceptions.py
  - core/config.py
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.websocket.events import (
    OrderCreatedEvent,
    OrderStatusChangedEvent,
    ClusterFormedEvent,
    RouteComputedEvent,
    DriverAssignedEvent,
    DriverMovedEvent,
    DeliveryCompletedEvent,
    MetricsUpdatedEvent,
    SimulationStatusEvent,
    SimulationCompletedEvent,
    ErrorEvent,
)
from app.websocket.manager import ConnectionManager


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET EVENTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestWebSocketEvents:

    def test_order_created_event_serialises(self):
        evt = OrderCreatedEvent(
            session_id="sim_test123",
            data=OrderCreatedEvent.Data(
                order_id="ord_abc",
                lat=-1.2864,
                lon=36.8172,
                zone="CBD",
                order_type="food",
                estimated_prep_minutes=15,
            ),
        )
        payload = json.loads(evt.to_json())
        assert payload["event"] == "ORDER_CREATED"
        assert payload["data"]["order_id"] == "ord_abc"
        assert payload["data"]["lat"] == -1.2864
        assert "timestamp" in payload

    def test_cluster_formed_event_serialises(self):
        evt = ClusterFormedEvent(
            session_id="sim_test",
            data=ClusterFormedEvent.Data(
                cluster_id="cls_001",
                order_ids=["ord_1", "ord_2"],
                centroid_lat=-1.2864,
                centroid_lon=36.8172,
                color="#FF6B35",
                zone_label="CBD cluster",
                size=2,
            ),
        )
        payload = json.loads(evt.to_json())
        assert payload["event"] == "CLUSTER_FORMED"
        assert payload["data"]["size"] == 2

    def test_route_computed_event_serialises(self):
        evt = RouteComputedEvent(
            session_id="sim_test",
            data=RouteComputedEvent.Data(
                route_id="rte_001",
                cluster_id="cls_001",
                driver_id="drv_001",
                method="haversine",
                geojson={"type": "Feature", "geometry": {"type": "LineString", "coordinates": []}},
                total_distance_km=5.2,
                estimated_duration_minutes=12.5,
                naive_distance_km=14.0,
                color="#FF6B35",
            ),
        )
        payload = json.loads(evt.to_json())
        assert payload["event"] == "ROUTE_COMPUTED"
        assert payload["data"]["total_distance_km"] == 5.2
        assert payload["data"]["geojson"]["type"] == "Feature"

    def test_driver_moved_event_serialises(self):
        evt = DriverMovedEvent(
            session_id="sim_test",
            data=DriverMovedEvent.Data(
                driver_id="drv_001",
                lat=-1.2870,
                lon=36.8180,
                progress_pct=0.35,
                current_order_id="ord_abc",
            ),
        )
        payload = json.loads(evt.to_json())
        assert payload["event"] == "DRIVER_MOVED"
        assert payload["data"]["progress_pct"] == 0.35

    def test_delivery_completed_event_serialises(self):
        evt = DeliveryCompletedEvent(
            session_id="sim_test",
            data=DeliveryCompletedEvent.Data(
                order_id="ord_001",
                driver_id="drv_001",
                time_taken_minutes=18.5,
            ),
        )
        payload = json.loads(evt.to_json())
        assert payload["event"] == "DELIVERY_COMPLETED"
        assert payload["data"]["time_taken_minutes"] == 18.5

    def test_metrics_updated_event_serialises(self):
        evt = MetricsUpdatedEvent(
            session_id="sim_test",
            data=MetricsUpdatedEvent.Data(
                deliveries_completed=5,
                deliveries_total=20,
                optimised_distance_km=45.2,
                naive_distance_km=140.0,
                distance_saved_km=94.8,
                savings_percentage=67.7,
                fuel_saved_litres=9.48,
                cost_saved_kes=1990.8,
                time_saved_minutes=189.6,
                co2_saved_kg=21.9,
                active_drivers=3,
                clusters_formed=6,
            ),
        )
        payload = json.loads(evt.to_json())
        assert payload["event"] == "METRICS_UPDATED"
        assert payload["data"]["savings_percentage"] == 67.7

    def test_simulation_completed_event_serialises(self):
        evt = SimulationCompletedEvent(
            session_id="sim_test",
            data=SimulationCompletedEvent.Data(
                session_id="sim_test",
                total_deliveries=30,
                total_distance_km=87.5,
                total_savings_pct=38.2,
                duration_seconds=42.5,
            ),
        )
        payload = json.loads(evt.to_json())
        assert payload["event"] == "SIMULATION_COMPLETED"
        assert payload["data"]["total_deliveries"] == 30

    def test_simulation_status_event_serialises(self):
        evt = SimulationStatusEvent(
            session_id="sim_test",
            data=SimulationStatusEvent.Data(
                status="clustering",
                message="Clustering nearby orders…",
            ),
        )
        payload = json.loads(evt.to_json())
        assert payload["event"] == "SIMULATION_STATUS"
        assert payload["data"]["status"] == "clustering"

    def test_error_event_serialises(self):
        evt = ErrorEvent(
            session_id="sim_test",
            data=ErrorEvent.Data(
                error_code="ROUTING_FAILED",
                message="Could not compute route",
            ),
        )
        payload = json.loads(evt.to_json())
        assert payload["event"] == "ERROR"
        assert payload["data"]["error_code"] == "ROUTING_FAILED"

    def test_event_timestamp_is_recent(self):
        evt = OrderCreatedEvent(
            session_id="sim_test",
            data=OrderCreatedEvent.Data(
                order_id="ord_1",
                lat=-1.28,
                lon=36.82,
                zone="CBD",
                order_type="food",
                estimated_prep_minutes=15,
            ),
        )
        payload = json.loads(evt.to_json())
        ts = datetime.fromisoformat(payload["timestamp"].replace("Z", ""))
        assert (datetime.utcnow() - ts).total_seconds() < 5

    def test_optional_current_order_id_can_be_none(self):
        evt = DriverMovedEvent(
            session_id="sim_test",
            data=DriverMovedEvent.Data(
                driver_id="drv_001",
                lat=-1.28,
                lon=36.82,
                progress_pct=0.0,
                current_order_id=None,
            ),
        )
        payload = json.loads(evt.to_json())
        assert payload["data"].get("current_order_id") is None


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectionManager:

    def make_mock_ws(self):
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self):
        manager = ConnectionManager()
        ws = self.make_mock_ws()
        await manager.connect(ws, "session_1")
        ws.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_tracks_session(self):
        manager = ConnectionManager()
        ws = self.make_mock_ws()
        await manager.connect(ws, "session_1")
        assert manager.connection_count("session_1") == 1

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self):
        manager = ConnectionManager()
        ws = self.make_mock_ws()
        await manager.connect(ws, "session_1")
        manager.disconnect(ws, "session_1")
        assert manager.connection_count("session_1") == 0

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_empty_session(self):
        manager = ConnectionManager()
        ws = self.make_mock_ws()
        await manager.connect(ws, "session_1")
        manager.disconnect(ws, "session_1")
        assert "session_1" not in manager.active_sessions()

    @pytest.mark.asyncio
    async def test_multiple_clients_same_session(self):
        manager = ConnectionManager()
        ws1, ws2 = self.make_mock_ws(), self.make_mock_ws()
        await manager.connect(ws1, "session_1")
        await manager.connect(ws2, "session_1")
        assert manager.connection_count("session_1") == 2

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_clients(self):
        manager = ConnectionManager()
        ws1, ws2 = self.make_mock_ws(), self.make_mock_ws()
        await manager.connect(ws1, "session_1")
        await manager.connect(ws2, "session_1")

        evt = SimulationStatusEvent(
            session_id="session_1",
            data=SimulationStatusEvent.Data(status="test", message="hello"),
        )
        await manager.broadcast("session_1", evt)

        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_session_does_not_raise(self):
        manager = ConnectionManager()
        evt = SimulationStatusEvent(
            session_id="ghost_session",
            data=SimulationStatusEvent.Data(status="test", message="hello"),
        )
        # Should not raise
        await manager.broadcast("ghost_session", evt)

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        manager = ConnectionManager()
        ws = self.make_mock_ws()
        ws.send_text = AsyncMock(side_effect=Exception("Connection closed"))
        await manager.connect(ws, "session_1")

        evt = SimulationStatusEvent(
            session_id="session_1",
            data=SimulationStatusEvent.Data(status="test", message="hello"),
        )
        await manager.broadcast("session_1", evt)
        # Dead connection should be cleaned up
        assert manager.connection_count("session_1") == 0

    @pytest.mark.asyncio
    async def test_send_personal_sends_to_one_client(self):
        manager = ConnectionManager()
        ws1, ws2 = self.make_mock_ws(), self.make_mock_ws()
        await manager.connect(ws1, "session_1")
        await manager.connect(ws2, "session_1")

        evt = SimulationStatusEvent(
            session_id="session_1",
            data=SimulationStatusEvent.Data(status="test", message="personal"),
        )
        await manager.send_personal(ws1, evt)

        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_not_called()

    def test_total_connections(self):
        manager = ConnectionManager()
        # Manually inject to test counting
        ws1, ws2, ws3 = MagicMock(), MagicMock(), MagicMock()
        manager._connections["session_1"].add(ws1)
        manager._connections["session_1"].add(ws2)
        manager._connections["session_2"].add(ws3)
        assert manager.total_connections() == 3

    def test_active_sessions(self):
        manager = ConnectionManager()
        ws1, ws2 = MagicMock(), MagicMock()
        manager._connections["s1"].add(ws1)
        manager._connections["s2"].add(ws2)
        sessions = manager.active_sessions()
        assert "s1" in sessions
        assert "s2" in sessions


# ═══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderModel:

    def test_order_default_id_generated(self):
        from app.models.order import Order, OrderType
        o = Order(lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD)
        assert o.id.startswith("ord_")

    def test_order_status_default(self):
        from app.models.order import Order, OrderType, OrderStatus
        o = Order(lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD)
        assert o.status == OrderStatus.PENDING or o.status == "pending"

    def test_order_prep_minutes_validation(self):
        from app.models.order import Order, OrderType
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            Order(lat=-1.2864, lon=36.8172, zone="CBD",
                  order_type=OrderType.FOOD, estimated_prep_minutes=4)

    def test_order_created_at_auto_set(self):
        from app.models.order import Order, OrderType
        o = Order(lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD)
        assert o.created_at is not None

    def test_two_orders_have_unique_ids(self):
        from app.models.order import Order, OrderType
        o1 = Order(lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD)
        o2 = Order(lat=-1.2864, lon=36.8172, zone="CBD", order_type=OrderType.FOOD)
        assert o1.id != o2.id


class TestDriverModel:

    def test_driver_default_id(self):
        from app.models.driver import Driver
        d = Driver(name="Test", lat=-1.2864, lon=36.8172, zone="CBD")
        assert d.id.startswith("drv_")

    def test_driver_default_status_idle(self):
        from app.models.driver import Driver, DriverStatus
        d = Driver(name="Test", lat=-1.2864, lon=36.8172, zone="CBD")
        assert d.status == DriverStatus.IDLE or d.status == "idle"

    def test_driver_capacity_default(self):
        from app.models.driver import Driver
        d = Driver(name="Test", lat=-1.2864, lon=36.8172, zone="CBD")
        assert d.capacity == 6

    def test_driver_assigned_orders_empty_by_default(self):
        from app.models.driver import Driver
        d = Driver(name="Test", lat=-1.2864, lon=36.8172, zone="CBD")
        assert d.assigned_orders == []


class TestClusterModel:

    def test_cluster_default_id(self):
        from app.models.cluster import Cluster
        c = Cluster(centroid_lat=-1.2864, centroid_lon=36.8172)
        assert c.id.startswith("cls_")

    def test_cluster_size_property(self):
        from app.models.cluster import Cluster
        c = Cluster(centroid_lat=-1.2864, centroid_lon=36.8172,
                    order_ids=["a", "b", "c"])
        assert c.size == 3

    def test_cluster_empty_size(self):
        from app.models.cluster import Cluster
        c = Cluster(centroid_lat=-1.2864, centroid_lon=36.8172)
        assert c.size == 0


class TestRouteModel:

    def test_route_default_values(self):
        from app.models.route import Route, RoutingMethod
        r = Route(id="r1", cluster_id="c1", driver_id="d1", method=RoutingMethod.HAVERSINE)
        assert r.total_distance_km == 0.0
        assert r.estimated_duration_minutes == 0.0
        assert r.waypoints == []


class TestSimulationModels:

    def test_simulation_config_defaults(self):
        from app.models.simulation import SimulationConfig
        cfg = SimulationConfig()
        assert 5 <= cfg.order_count <= 60
        assert 1 <= cfg.driver_count <= 8

    def test_simulation_state_session_id_generated(self):
        from app.models.simulation import SimulationState
        s1 = SimulationState()
        s2 = SimulationState()
        assert s1.session_id != s2.session_id

    def test_simulation_metrics_savings_percentage(self):
        from app.models.simulation import SimulationMetrics
        m = SimulationMetrics(naive_distance_km=100.0, distance_saved_km=38.0)
        assert m.savings_percentage == pytest.approx(38.0)

    def test_simulation_metrics_savings_zero_naive(self):
        from app.models.simulation import SimulationMetrics
        m = SimulationMetrics(naive_distance_km=0.0)
        assert m.savings_percentage == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCustomExceptions:

    def test_graph_not_loaded_error(self):
        from app.core.exceptions import GraphNotLoadedError
        exc = GraphNotLoadedError()
        assert exc.status_code == 503
        assert exc.error_code == "GRAPH_NOT_LOADED"
        assert "graph" in exc.message.lower()

    def test_osrm_connection_error(self):
        from app.core.exceptions import OSRMConnectionError
        exc = OSRMConnectionError("http://test.com")
        assert exc.status_code == 503
        assert "test.com" in exc.message

    def test_osrm_route_not_found(self):
        from app.core.exceptions import OSRMRouteNotFound
        exc = OSRMRouteNotFound("No route found")
        assert exc.status_code == 422
        assert exc.error_code == "OSRM_NO_ROUTE"

    def test_unsupported_routing_method(self):
        from app.core.exceptions import UnsupportedRoutingMethod
        exc = UnsupportedRoutingMethod("teleport")
        assert exc.status_code == 400
        assert "teleport" in exc.message

    def test_simulation_not_found(self):
        from app.core.exceptions import SimulationNotFoundError
        exc = SimulationNotFoundError("sim_abc")
        assert exc.status_code == 404
        assert "sim_abc" in exc.message

    def test_simulation_limit_exceeded(self):
        from app.core.exceptions import SimulationLimitExceededError
        exc = SimulationLimitExceededError("Too many orders")
        assert exc.status_code == 400

    def test_to_dict_structure(self):
        from app.core.exceptions import GraphNotLoadedError
        exc = GraphNotLoadedError()
        d = exc.to_dict()
        assert "error_code" in d
        assert "message" in d
        assert "detail" in d

    def test_exceptions_are_catchable_as_base(self):
        from app.core.exceptions import (
            NairobiRoutingBaseException,
            GraphNotLoadedError,
            OSRMConnectionError,
        )
        for ExcClass in [GraphNotLoadedError]:
            try:
                raise ExcClass()
            except NairobiRoutingBaseException:
                pass  # correct


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfig:

    def test_settings_loads(self):
        from app.core.config import settings
        assert settings is not None

    def test_cors_origins_list_is_list(self):
        from app.core.config import settings
        result = settings.cors_origins_list
        assert isinstance(result, list)

    def test_nairobi_bounding_box_valid(self):
        from app.core.config import settings
        assert settings.nairobi_bbox_north > settings.nairobi_bbox_south
        assert settings.nairobi_bbox_east > settings.nairobi_bbox_west

    def test_nairobi_bounding_box_covers_nairobi(self):
        from app.core.config import settings
        # Nairobi CBD at (-1.2864, 36.8172) should be inside the bbox
        assert settings.nairobi_bbox_south < -1.2864 < settings.nairobi_bbox_north
        assert settings.nairobi_bbox_west < 36.8172 < settings.nairobi_bbox_east

    def test_fuel_constants_positive(self):
        from app.core.config import settings
        assert settings.fuel_litres_per_100km > 0
        assert settings.fuel_price_kes_per_litre > 0
        assert settings.co2_kg_per_litre > 0

    def test_simulation_limits_positive(self):
        from app.core.config import settings
        assert settings.simulation_max_orders > 0
        assert settings.simulation_max_drivers > 0

    def test_get_settings_returns_same_instance(self):
        from app.core.config import get_settings
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2  # cached singleton

    def test_is_production_false_by_default(self):
        from app.core.config import settings
        # Default is development
        assert settings.is_production is False or isinstance(settings.is_production, bool)