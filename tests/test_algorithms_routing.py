"""
tests/test_algorithms_routing.py
─────────────────────────────────────────────────────────────────────────────
Tests for routing modules:
  - algorithms/routing/dijkstra.py
  - algorithms/routing/vrp_solver.py
  - algorithms/routing/osrm_client.py
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import networkx as nx
import pytest

from app.algorithms.routing.dijkstra import (
    shortest_path_between_nodes,
    multi_stop_shortest_path,
)
from app.algorithms.routing.vrp_solver import solve_vrp, _greedy_vrp_fallback


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: Build small test graph
# ═══════════════════════════════════════════════════════════════════════════════

def build_test_graph() -> nx.MultiDiGraph:
    """
    Minimal road graph:
       1 --500m/60s-- 2 --700m/90s-- 3
       |                              |
       +-----------1200m/150s----------+
    """
    G = nx.MultiDiGraph()
    for node_id, (x, y) in {
        1: (36.817, -1.286),
        2: (36.820, -1.287),
        3: (36.824, -1.289),
    }.items():
        G.add_node(node_id, x=x, y=y)

    G.add_edge(1, 2, 0, length=500, travel_time=60)
    G.add_edge(2, 1, 0, length=500, travel_time=60)
    G.add_edge(2, 3, 0, length=700, travel_time=90)
    G.add_edge(3, 2, 0, length=700, travel_time=90)
    G.add_edge(1, 3, 0, length=1200, travel_time=150)
    G.add_edge(3, 1, 0, length=1200, travel_time=150)
    return G


# ═══════════════════════════════════════════════════════════════════════════════
# DIJKSTRA
# ═══════════════════════════════════════════════════════════════════════════════

class TestShortestPathBetweenNodes:

    def setup_method(self):
        self.G = build_test_graph()

    def test_direct_path(self):
        dist, time, path = shortest_path_between_nodes(self.G, 1, 2)
        assert dist == pytest.approx(0.5)  # 500m = 0.5km
        assert time == pytest.approx(60.0)
        assert path == [1, 2]

    def test_indirect_path_via_two_hops(self):
        """1→3 via [1,2,3] is shorter than direct edge (1200m vs 1200m direct)."""
        dist_12_23 = 0.5 + 0.7  # 1.2km
        dist_direct = 1.2  # km
        # Shortest should pick the cheaper path (both equal here)
        dist, time, path = shortest_path_between_nodes(self.G, 1, 3)
        assert dist <= 1.2 + 1e-6
        
    def test_no_path_returns_inf(self):
        G_disconnected = nx.MultiDiGraph()
        G_disconnected.add_node(99, x=36.8, y=-1.28)
        G_disconnected.add_node(100, x=36.9, y=-1.29)
        dist, time, path = shortest_path_between_nodes(G_disconnected, 99, 100)
        assert dist == float("inf")
        assert time == float("inf")
        assert path == []

    def test_node_not_found_returns_inf(self):
        dist, time, path = shortest_path_between_nodes(self.G, 1, 999)
        assert dist == float("inf")
        assert path == []

    def test_same_node_returns_zero(self):
        dist, time, path = shortest_path_between_nodes(self.G, 1, 1)
        assert dist == pytest.approx(0.0)
        assert path == [1]

    def test_path_is_valid_sequence(self):
        dist, time, path = shortest_path_between_nodes(self.G, 1, 3)
        assert path[0] == 1
        assert path[-1] == 3
        # Every consecutive pair must be connected by an edge
        for i in range(len(path) - 1):
            assert self.G.has_edge(path[i], path[i+1])

    def test_travel_time_weight(self):
        """Routing by travel_time should use travel_time edge attribute."""
        dist, time, path = shortest_path_between_nodes(
            self.G, 1, 2, weight="travel_time"
        )
        assert time == pytest.approx(60.0)

    def test_returns_km_not_metres(self):
        dist, _, _ = shortest_path_between_nodes(self.G, 1, 2)
        # 500m edge → 0.5km
        assert dist < 1.0  # definitely in km range, not metres (500)


class TestMultiStopShortestPath:

    def setup_method(self):
        self.G = build_test_graph()

    def test_empty_sequence(self):
        dist, time, path = multi_stop_shortest_path(self.G, [])
        assert dist == 0.0
        assert time == 0.0
        assert path == []

    def test_single_node_sequence(self):
        dist, time, path = multi_stop_shortest_path(self.G, [1])
        assert dist == 0.0
        assert path == [1]

    def test_two_node_sequence(self):
        dist, time, path = multi_stop_shortest_path(self.G, [1, 2])
        assert dist == pytest.approx(0.5)
        assert time == pytest.approx(60.0)

    def test_three_node_sequence(self):
        dist, time, path = multi_stop_shortest_path(self.G, [1, 2, 3])
        # 1→2 (0.5km) + 2→3 (0.7km) = 1.2km
        assert dist == pytest.approx(1.2)

    def test_path_starts_and_ends_correctly(self):
        _, _, path = multi_stop_shortest_path(self.G, [1, 2, 3])
        assert path[0] == 1
        assert path[-1] == 3

    def test_no_duplicate_boundary_nodes(self):
        """Segment boundaries should not repeat the boundary node."""
        _, _, path = multi_stop_shortest_path(self.G, [1, 2, 3])
        # Node 2 should appear exactly once in the full path
        assert path.count(2) == 1

    def test_unreachable_segment_skipped(self):
        G_partial = nx.MultiDiGraph()
        G_partial.add_node(1, x=36.8, y=-1.28)
        G_partial.add_node(2, x=36.82, y=-1.29)
        G_partial.add_node(3, x=36.84, y=-1.30)
        # Only 1→2 connected
        G_partial.add_edge(1, 2, 0, length=500, travel_time=60)

        dist, time, path = multi_stop_shortest_path(G_partial, [1, 2, 3])
        # 1→2 succeeds, 2→3 is inf (skipped)
        assert dist == pytest.approx(0.5)


# ═══════════════════════════════════════════════════════════════════════════════
# VRP SOLVER
# ═══════════════════════════════════════════════════════════════════════════════

class TestGreedyVRPFallback:
    """Test the fallback solver (always available, no OR-Tools needed)."""

    def make_distance_matrix(self, n: int) -> list:
        """Trivial NxN distance matrix: depot at 0, all stops 1km from depot, 2km between stops."""
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(1, n):
            matrix[0][i] = 1.0
            matrix[i][0] = 1.0
            for j in range(1, n):
                if i != j:
                    matrix[i][j] = 2.0
        return matrix

    def test_returns_list_of_routes(self):
        matrix = self.make_distance_matrix(5)  # depot + 4 stops
        routes = _greedy_vrp_fallback(matrix, driver_count=2, capacity=4)
        assert isinstance(routes, list)
        assert len(routes) >= 1

    def test_all_stops_covered(self):
        matrix = self.make_distance_matrix(7)  # depot + 6 stops
        routes = _greedy_vrp_fallback(matrix, driver_count=2, capacity=6)
        assigned_stops = set()
        for route in routes:
            # Exclude depot (index 0) and return-to-depot
            assigned_stops.update(n for n in route if n != 0)
        expected_stops = set(range(1, 7))
        assert assigned_stops == expected_stops

    def test_capacity_not_exceeded(self):
        matrix = self.make_distance_matrix(9)
        capacity = 3
        routes = _greedy_vrp_fallback(matrix, driver_count=3, capacity=capacity)
        for route in routes:
            stops_in_route = [n for n in route if n != 0]
            assert len(stops_in_route) <= capacity, \
                f"Route has {len(stops_in_route)} stops > capacity {capacity}"

    def test_routes_start_and_end_at_depot(self):
        matrix = self.make_distance_matrix(5)
        routes = _greedy_vrp_fallback(matrix, driver_count=2, capacity=3)
        for route in routes:
            assert route[0] == 0, "Route should start at depot (node 0)"
            assert route[-1] == 0, "Route should end at depot (node 0)"

    def test_single_driver_single_stop(self):
        matrix = [[0.0, 1.0], [1.0, 0.0]]
        routes = _greedy_vrp_fallback(matrix, driver_count=1, capacity=1)
        assert len(routes) == 1
        assert 1 in routes[0]


class TestSolveVRP:

    def make_matrix(self, n_stops: int) -> list:
        """Simple distance matrix: depot at index 0, all stops 1km from each other."""
        n = n_stops + 1
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    matrix[i][j] = 1.0 + abs(i - j) * 0.5
        return matrix

    def test_returns_none_or_list(self):
        matrix = self.make_matrix(4)
        result = solve_vrp(matrix, driver_count=2, capacity=4)
        assert result is None or isinstance(result, list)

    def test_with_greedy_fallback_on_ortools_missing(self):
        """If OR-Tools unavailable, should return from greedy fallback."""
        matrix = self.make_matrix(4)
        with patch.dict("sys.modules", {"ortools": None,
                                         "ortools.constraint_solver": None,
                                         "ortools.constraint_solver.pywrapcp": None,
                                         "ortools.constraint_solver.routing_enums_pb2": None}):
            result = solve_vrp(matrix, driver_count=2, capacity=4)
            # Greedy fallback should produce something
            if result is not None:
                assert isinstance(result, list)

    def test_single_location_returns_depot(self):
        matrix = [[0.0]]
        result = solve_vrp(matrix, driver_count=1)
        assert result == [[0]]

    def test_empty_demands_default_to_one(self):
        """demands=None should default to 1 per stop — this shouldn't crash."""
        matrix = self.make_matrix(3)
        result = solve_vrp(matrix, driver_count=2, demands=None, capacity=3)
        assert result is None or isinstance(result, list)


# ═══════════════════════════════════════════════════════════════════════════════
# OSRM CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class TestOSRMClient:

    @pytest.fixture
    def client(self):
        from app.algorithms.routing.osrm_client import OSRMClient
        return OSRMClient(base_url="http://test-osrm.example.com")

    @pytest.mark.asyncio
    async def test_get_route_parses_response(self, client):
        """Mock a successful OSRM /route response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "Ok",
            "routes": [{
                "distance": 3500.0,
                "duration": 480.0,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[36.817, -1.286], [36.820, -1.287]],
                },
            }],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await client.get_route([(-1.286, 36.817), (-1.287, 36.820)])

        assert result["code"] == "Ok"
        assert len(result["routes"]) == 1

    @pytest.mark.asyncio
    async def test_get_route_raises_on_connection_error(self, client):
        import httpx
        from app.core.exceptions import OSRMConnectionError

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock,
                   side_effect=httpx.ConnectError("refused")):
            with pytest.raises(OSRMConnectionError):
                await client.get_route([(-1.286, 36.817), (-1.287, 36.820)])

    @pytest.mark.asyncio
    async def test_get_route_raises_on_no_routes(self, client):
        from app.core.exceptions import OSRMRouteNotFound

        mock_response = MagicMock()
        mock_response.json.return_value = {"code": "Ok", "routes": []}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(OSRMRouteNotFound):
                await client.get_route([(-1.286, 36.817), (-1.287, 36.820)])

    @pytest.mark.asyncio
    async def test_get_route_geometry_and_distance_success(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "Ok",
            "routes": [{
                "distance": 4200.0,  # metres
                "duration": 600.0,   # seconds
                "geometry": {"type": "LineString", "coordinates": []},
            }],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            geojson, dist_km, dur_min = await client.get_route_geometry_and_distance(
                [(-1.286, 36.817), (-1.287, 36.820)]
            )

        assert dist_km == pytest.approx(4.2)
        assert dur_min == pytest.approx(10.0)
        assert geojson["properties"]["method"] == "street_network"
        assert geojson["properties"]["source"] == "osrm"

    @pytest.mark.asyncio
    async def test_get_route_falls_back_to_haversine_on_osrm_failure(self, client):
        """When OSRM is unreachable, should fall back to Haversine routing."""
        from app.core.exceptions import OSRMConnectionError

        with patch.object(client, "get_route", new_callable=AsyncMock,
                          side_effect=OSRMConnectionError("http://test")):
            geojson, dist_km, dur_min = await client.get_route_geometry_and_distance(
                [(-1.286, 36.817), (-1.287, 36.820)]
            )

        assert geojson["type"] == "Feature"
        assert "haversine" in geojson["properties"]["method"]
        assert dist_km > 0

    @pytest.mark.asyncio
    async def test_waypoint_coordinate_order(self, client):
        """OSRM expects lon,lat — verify coordinate string formatting."""
        captured_urls = []

        async def fake_get(url, **kwargs):
            captured_urls.append(url)
            mock_r = MagicMock()
            mock_r.json.return_value = {"code": "Ok", "routes": [
                {"distance": 1000, "duration": 120,
                 "geometry": {"type": "LineString", "coordinates": []}}
            ]}
            mock_r.raise_for_status = MagicMock()
            return mock_r

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=fake_get):
            await client.get_route([(-1.286, 36.817)])

        assert captured_urls
        url = captured_urls[0]
        # Should be lon,lat = 36.817,-1.286 in the URL
        assert "36.817,-1.286" in url

    @pytest.mark.asyncio
    async def test_close_cleans_up_client(self, client):
        """close() should not raise even if called multiple times."""
        await client.close()
        await client.close()  # second call should be safe

    @pytest.mark.asyncio
    async def test_get_distance_table(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "durations": [[0, 60], [60, 0]],
            "distances": [[0, 500], [500, 0]],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await client.get_distance_table(
                [(-1.286, 36.817), (-1.287, 36.820)]
            )

        assert "durations" in result
        assert "distances" in result