"""
tests/test_algorithms_distance.py
─────────────────────────────────────────────────────────────────────────────
Tests for all three distance modules:
  - algorithms/distance/euclidean.py
  - algorithms/distance/haversine.py
  - algorithms/distance/street_network.py
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from app.algorithms.distance.euclidean import (
    euclidean_distance,
    euclidean_distance_matrix,
    nearest_neighbour_tour,
    build_euclidean_geojson,
)
from app.algorithms.distance.haversine import (
    haversine_distance,
    haversine_distance_matrix,
    nearest_neighbour_tour_haversine,
    build_haversine_geojson,
    total_route_distance,
    EARTH_RADIUS_KM,
)


# ═══════════════════════════════════════════════════════════════════════════════
# EUCLIDEAN DISTANCE
# ═══════════════════════════════════════════════════════════════════════════════

class TestEuclideanDistance:

    def test_same_point_is_zero(self):
        assert euclidean_distance(-1.2864, 36.8172, -1.2864, 36.8172) == pytest.approx(0.0)

    def test_returns_positive_value(self):
        d = euclidean_distance(-1.2864, 36.8172, -1.2676, 36.8037)
        assert d > 0

    def test_symmetry(self):
        """Distance A→B must equal distance B→A."""
        d1 = euclidean_distance(-1.2864, 36.8172, -1.2676, 36.8037)
        d2 = euclidean_distance(-1.2676, 36.8037, -1.2864, 36.8172)
        assert d1 == pytest.approx(d2)

    def test_nairobi_cbd_to_westlands_rough_range(self):
        """CBD to Westlands is ~3 km straight-line; Euclidean should be near this."""
        d = euclidean_distance(-1.2864, 36.8172, -1.2676, 36.8037)
        assert 1.5 < d < 6.0, f"Expected 1.5–6km, got {d:.2f}km"

    def test_units_are_km(self):
        """1 degree of latitude ≈ 111 km — distance for 1° shift should be ~111 km."""
        d = euclidean_distance(0.0, 0.0, 1.0, 0.0)
        assert d == pytest.approx(111.0, rel=0.01)

    def test_distance_increases_with_separation(self):
        """Further points should produce larger distances."""
        d_close = euclidean_distance(-1.2864, 36.8172, -1.2870, 36.8175)
        d_far = euclidean_distance(-1.2864, 36.8172, -1.3500, 36.6900)
        assert d_far > d_close


class TestEuclideanDistanceMatrix:

    def test_shape(self, spread_coords):
        matrix = euclidean_distance_matrix(spread_coords)
        n = len(spread_coords)
        assert matrix.shape == (n, n)

    def test_diagonal_is_zero(self, spread_coords):
        matrix = euclidean_distance_matrix(spread_coords)
        np.testing.assert_array_almost_equal(np.diag(matrix), 0)

    def test_symmetry(self, spread_coords):
        matrix = euclidean_distance_matrix(spread_coords)
        np.testing.assert_array_almost_equal(matrix, matrix.T)

    def test_all_non_negative(self, spread_coords):
        matrix = euclidean_distance_matrix(spread_coords)
        assert (matrix >= 0).all()

    def test_single_point(self):
        coords = np.array([[-1.2864, 36.8172]])
        matrix = euclidean_distance_matrix(coords)
        assert matrix.shape == (1, 1)
        assert matrix[0, 0] == pytest.approx(0.0)

    def test_two_points_matches_direct_call(self):
        coords = np.array([[-1.2864, 36.8172], [-1.2676, 36.8037]])
        matrix = euclidean_distance_matrix(coords)
        direct = euclidean_distance(-1.2864, 36.8172, -1.2676, 36.8037)
        assert matrix[0, 1] == pytest.approx(direct)


class TestNearestNeighbourTourEuclidean:

    def test_empty_returns_empty(self):
        tour, dist = nearest_neighbour_tour(np.array([]).reshape(0, 2))
        assert tour == []
        assert dist == 0.0

    def test_single_point(self):
        coords = np.array([[-1.2864, 36.8172]])
        tour, dist = nearest_neighbour_tour(coords)
        assert tour == [0]
        assert dist == 0.0

    def test_tour_visits_all_points(self, spread_coords):
        tour, dist = nearest_neighbour_tour(spread_coords)
        assert len(tour) == len(spread_coords)
        assert sorted(tour) == list(range(len(spread_coords)))

    def test_tour_starts_at_start_idx(self, spread_coords):
        for start in range(len(spread_coords)):
            tour, _ = nearest_neighbour_tour(spread_coords, start_idx=start)
            assert tour[0] == start

    def test_distance_is_positive(self, spread_coords):
        _, dist = nearest_neighbour_tour(spread_coords)
        assert dist > 0

    def test_closed_tour(self, cbd_coords):
        """Distance includes return to start."""
        tour, dist = nearest_neighbour_tour(cbd_coords)
        # Recompute manually
        matrix = euclidean_distance_matrix(cbd_coords)
        manual = sum(matrix[tour[i], tour[i+1]] for i in range(len(tour)-1))
        manual += matrix[tour[-1], tour[0]]
        assert dist == pytest.approx(manual, rel=1e-6)


class TestBuildEuclideanGeoJSON:

    def test_valid_geojson_feature(self, spread_coords):
        tour = list(range(len(spread_coords)))
        result = build_euclidean_geojson(spread_coords, tour)
        assert result["type"] == "Feature"
        assert result["geometry"]["type"] == "LineString"
        assert result["properties"]["method"] == "euclidean"

    def test_coordinates_are_lon_lat(self, spread_coords):
        """GeoJSON uses [lon, lat] — lon is index 1 in the coords array."""
        tour = [0, 1]
        result = build_euclidean_geojson(spread_coords, tour)
        first_coord = result["geometry"]["coordinates"][0]
        # For spread_coords[0] = [-1.2864, 36.8172]:  lon=36.8172, lat=-1.2864
        assert first_coord[0] == pytest.approx(36.8172)  # lon
        assert first_coord[1] == pytest.approx(-1.2864)  # lat

    def test_tour_is_closed(self, spread_coords):
        tour = list(range(len(spread_coords)))
        result = build_euclidean_geojson(spread_coords, tour)
        coords = result["geometry"]["coordinates"]
        # Last point should match first
        assert coords[0] == coords[-1]

    def test_empty_tour(self, spread_coords):
        result = build_euclidean_geojson(spread_coords, [])
        assert result["geometry"]["coordinates"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# HAVERSINE DISTANCE
# ═══════════════════════════════════════════════════════════════════════════════

class TestHaversineDistance:

    def test_same_point_is_zero(self):
        assert haversine_distance(-1.2864, 36.8172, -1.2864, 36.8172) == pytest.approx(0.0)

    def test_returns_positive(self):
        d = haversine_distance(-1.2864, 36.8172, -1.2676, 36.8037)
        assert d > 0

    def test_symmetry(self):
        d1 = haversine_distance(-1.2864, 36.8172, -1.2676, 36.8037)
        d2 = haversine_distance(-1.2676, 36.8037, -1.2864, 36.8172)
        assert d1 == pytest.approx(d2, rel=1e-9)

    def test_cbd_to_westlands_realistic(self):
        """CBD to Westlands straight-line ≈ 2.5–4 km."""
        d = haversine_distance(-1.2864, 36.8172, -1.2676, 36.8037)
        assert 2.0 < d < 5.0, f"Expected 2–5km, got {d:.3f}km"

    def test_nairobi_to_mombasa(self):
        """Nairobi→Mombasa ≈ 440 km by air."""
        d = haversine_distance(-1.2864, 36.8172, -4.0435, 39.6682)
        assert 430 < d < 460, f"Expected ~440km, got {d:.1f}km"

    def test_haversine_larger_than_euclidean_for_long_distances(self):
        """For Nairobi→Mombasa, Haversine > Euclidean due to curvature."""
        hav = haversine_distance(-1.2864, 36.8172, -4.0435, 39.6682)
        euc = euclidean_distance(-1.2864, 36.8172, -4.0435, 39.6682)
        assert hav > euc  # curvature correction always adds distance

    def test_earth_radius_constant(self):
        assert EARTH_RADIUS_KM == pytest.approx(6371.0)

    def test_one_degree_latitude(self):
        """1° latitude ≈ 111.195 km on Haversine."""
        d = haversine_distance(0.0, 0.0, 1.0, 0.0)
        assert d == pytest.approx(111.195, rel=0.001)

    def test_haversine_vs_euclidean_close_range(self):
        """For short Nairobi intra-city distances, both should be within 1%."""
        hav = haversine_distance(-1.2864, 36.8172, -1.2870, 36.8180)
        euc = euclidean_distance(-1.2864, 36.8172, -1.2870, 36.8180)
        assert abs(hav - euc) / max(hav, 0.001) < 0.02  # within 2%


class TestHaversineDistanceMatrix:

    def test_shape(self, spread_coords):
        matrix = haversine_distance_matrix(spread_coords)
        assert matrix.shape == (len(spread_coords), len(spread_coords))

    def test_diagonal_is_zero(self, spread_coords):
        matrix = haversine_distance_matrix(spread_coords)
        np.testing.assert_array_almost_equal(np.diag(matrix), 0)

    def test_symmetric(self, spread_coords):
        matrix = haversine_distance_matrix(spread_coords)
        np.testing.assert_array_almost_equal(matrix, matrix.T)

    def test_matches_direct_calculation(self, spread_coords):
        matrix = haversine_distance_matrix(spread_coords)
        for i in range(len(spread_coords)):
            for j in range(len(spread_coords)):
                direct = haversine_distance(
                    spread_coords[i, 0], spread_coords[i, 1],
                    spread_coords[j, 0], spread_coords[j, 1],
                )
                assert matrix[i, j] == pytest.approx(direct, rel=1e-9)


class TestNearestNeighbourTourHaversine:

    def test_empty(self):
        tour, dist = nearest_neighbour_tour_haversine(np.array([]).reshape(0, 2))
        assert tour == []
        assert dist == 0.0

    def test_single_point(self):
        coords = np.array([[-1.2864, 36.8172]])
        tour, dist = nearest_neighbour_tour_haversine(coords)
        assert tour == [0]
        assert dist == 0.0

    def test_visits_all_points(self, spread_coords):
        tour, _ = nearest_neighbour_tour_haversine(spread_coords)
        assert len(tour) == len(spread_coords)
        assert sorted(tour) == list(range(len(spread_coords)))

    def test_start_index(self, spread_coords):
        for start in range(len(spread_coords)):
            tour, _ = nearest_neighbour_tour_haversine(spread_coords, start_idx=start)
            assert tour[0] == start

    def test_returns_positive_distance(self, spread_coords):
        _, dist = nearest_neighbour_tour_haversine(spread_coords)
        assert dist > 0

    def test_cbd_cluster_short_tour(self, cbd_coords):
        """Tightly clustered CBD points should yield a short total tour."""
        _, dist = nearest_neighbour_tour_haversine(cbd_coords)
        assert dist < 5.0, f"CBD cluster tour too long: {dist:.2f}km"


class TestTotalRouteDistance:

    def test_empty_list(self):
        assert total_route_distance([]) == 0.0

    def test_single_point(self):
        assert total_route_distance([(-1.2864, 36.8172)]) == 0.0

    def test_two_points_matches_direct(self):
        a, b = (-1.2864, 36.8172), (-1.2676, 36.8037)
        result = total_route_distance([a, b])
        direct = haversine_distance(a[0], a[1], b[0], b[1])
        assert result == pytest.approx(direct)

    def test_three_point_route(self):
        a = (-1.2864, 36.8172)
        b = (-1.2676, 36.8037)
        c = (-1.3031, 36.7877)
        total = total_route_distance([a, b, c])
        expected = haversine_distance(*a, *b) + haversine_distance(*b, *c)
        assert total == pytest.approx(expected, rel=1e-6)


class TestBuildHaversineGeoJSON:

    def test_valid_feature(self, spread_coords):
        tour = list(range(len(spread_coords)))
        result = build_haversine_geojson(spread_coords, tour)
        assert result["type"] == "Feature"
        assert result["geometry"]["type"] == "LineString"
        assert result["properties"]["method"] == "haversine"

    def test_lon_lat_order(self, spread_coords):
        tour = [0]
        result = build_haversine_geojson(spread_coords, tour)
        coord = result["geometry"]["coordinates"][0]
        # spread_coords[0] = [-1.2864, 36.8172] → [lon=36.8172, lat=-1.2864]
        assert coord[0] == pytest.approx(36.8172)
        assert coord[1] == pytest.approx(-1.2864)

    def test_closed_loop(self, spread_coords):
        tour = list(range(len(spread_coords)))
        result = build_haversine_geojson(spread_coords, tour)
        coords = result["geometry"]["coordinates"]
        assert coords[0] == coords[-1]


# ═══════════════════════════════════════════════════════════════════════════════
# STREET NETWORK (light unit tests — no real graph required)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStreetNetworkHelpers:
    """
    Test street_network.py helpers that don't require a live graph.
    Graph-dependent functions (shortest_path_distance, street_distance_matrix)
    are tested with mock graphs.
    """

    def test_shortest_path_distance_no_path(self):
        """Returns (inf, inf, []) when no path exists."""
        import networkx as nx
        from app.algorithms.distance.street_network import shortest_path_distance

        G = nx.MultiDiGraph()
        G.add_node(1, x=36.8, y=-1.28)
        G.add_node(2, x=36.9, y=-1.29)
        # No edge — no path

        dist, time, path = shortest_path_distance(G, 1, 2)
        assert dist == float("inf")
        assert time == float("inf")
        assert path == []

    def test_shortest_path_distance_with_path(self):
        import networkx as nx
        from app.algorithms.distance.street_network import shortest_path_distance

        G = nx.MultiDiGraph()
        G.add_node(1, x=36.817, y=-1.286)
        G.add_node(2, x=36.820, y=-1.287)
        G.add_edge(1, 2, 0, length=500, travel_time=60)

        dist, time, path = shortest_path_distance(G, 1, 2, weight="travel_time")
        assert dist == pytest.approx(0.5)
        assert time == pytest.approx(60.0)
        assert path == [1, 2]

    def test_path_to_geojson_uses_geometry_when_available(self):
        import networkx as nx
        from shapely.geometry import LineString
        from app.algorithms.distance.street_network import path_to_geojson_coordinates

        G = nx.MultiDiGraph()
        G.add_node(1, x=36.817, y=-1.286)
        G.add_node(2, x=36.820, y=-1.287)
        geom = LineString([(36.817, -1.286), (36.818, -1.2865), (36.820, -1.287)])
        G.add_edge(1, 2, 0, length=500, geometry=geom)

        coords = path_to_geojson_coordinates(G, [1, 2])
        assert len(coords) >= 2
        # All coordinates should be [lon, lat] floats
        for c in coords:
            assert len(c) == 2

    def test_build_street_network_geojson_structure(self):
        import networkx as nx
        from app.algorithms.distance.street_network import build_street_network_geojson

        G = nx.MultiDiGraph()
        G.add_node(1, x=36.817, y=-1.286)
        G.add_node(2, x=36.820, y=-1.287)
        G.add_edge(1, 2, 0, length=500)

        result = build_street_network_geojson(G, [1, 2])
        assert result["type"] == "Feature"
        assert result["geometry"]["type"] == "LineString"
        assert result["properties"]["method"] == "street_network"

    def test_street_distance_matrix_shape(self):
        import networkx as nx
        from app.algorithms.distance.street_network import street_distance_matrix

        G = nx.MultiDiGraph()
        for i, (x, y) in enumerate([(36.8, -1.28), (36.82, -1.29), (36.84, -1.30)]):
            G.add_node(i, x=x, y=y)
        G.add_edge(0, 1, 0, length=500, travel_time=60)
        G.add_edge(1, 2, 0, length=700, travel_time=90)
        G.add_edge(0, 2, 0, length=1200, travel_time=150)

        node_ids = [0, 1, 2]
        dist_matrix, time_matrix = street_distance_matrix(G, node_ids)
        assert len(dist_matrix) == 3
        assert len(dist_matrix[0]) == 3
        assert dist_matrix[0][0] == 0.0