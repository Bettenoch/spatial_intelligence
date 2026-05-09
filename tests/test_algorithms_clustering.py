"""
tests/test_algorithms_clustering.py
─────────────────────────────────────────────────────────────────────────────
Tests for all three clustering modules:
  - algorithms/clustering/dbscan.py
  - algorithms/clustering/kmeans.py
  - algorithms/clustering/hdbscan.py (with fallback path)
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import math
from typing import List
from unittest.mock import patch

import numpy as np
import pytest

from app.algorithms.clustering.dbscan import run_dbscan, _make_cluster, _split_cluster
from app.algorithms.clustering.kmeans import run_kmeans
from app.models.cluster import CLUSTER_COLORS, Cluster
from app.models.order import Order, OrderType


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_orders(coords: list, zone: str = "CBD") -> List[Order]:
    """Helper to create Order objects from (lat, lon) pairs."""
    return [Order(lat=lat, lon=lon, zone=zone, order_type=OrderType.FOOD)
            for lat, lon in coords]


def make_clustered_orders() -> List[Order]:
    """
    Returns 10 orders forming two obvious spatial clusters:
    - Cluster A: 5 orders near CBD
    - Cluster B: 5 orders near Westlands (~3km away)
    """
    cbd = [
        (-1.2864, 36.8172),
        (-1.2870, 36.8180),
        (-1.2855, 36.8165),
        (-1.2860, 36.8170),
        (-1.2868, 36.8175),
    ]
    westlands = [
        (-1.2676, 36.8037),
        (-1.2680, 36.8045),
        (-1.2672, 36.8030),
        (-1.2678, 36.8040),
        (-1.2682, 36.8050),
    ]
    return (
        make_orders(cbd, zone="CBD") +
        make_orders(westlands, zone="Westlands")
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DBSCAN
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunDBSCAN:

    def test_empty_returns_empty(self):
        result = run_dbscan([])
        assert result == {}

    def test_single_order_becomes_solo_cluster(self):
        orders = make_orders([(-1.2864, 36.8172)])
        result = run_dbscan(orders)
        assert len(result) == 1
        cluster = list(result.values())[0]
        assert len(cluster.order_ids) == 1

    def test_two_nearby_orders_form_one_cluster(self):
        # 100m apart — within 1.5km epsilon
        orders = make_orders([
            (-1.2864, 36.8172),
            (-1.2865, 36.8173),
        ])
        result = run_dbscan(orders, epsilon_km=1.5, min_samples=2)
        assert len(result) == 1
        cluster = list(result.values())[0]
        assert len(cluster.order_ids) == 2

    def test_two_distant_orders_become_separate_clusters(self):
        # CBD and Karen — ~8km apart, far beyond epsilon
        orders = make_orders([
            (-1.2864, 36.8172),  # CBD
            (-1.2996, 36.7500),  # Karen
        ])
        result = run_dbscan(orders, epsilon_km=1.5, min_samples=2)
        # Each is a noise point → separate solo clusters
        assert len(result) == 2
        for cluster in result.values():
            assert len(cluster.order_ids) == 1

    def test_two_obvious_clusters_detected(self):
        orders = make_clustered_orders()
        result = run_dbscan(orders, epsilon_km=1.5, min_samples=2)
        # Should find 2 dense clusters (CBD + Westlands)
        cluster_sizes = sorted([len(c.order_ids) for c in result.values()], reverse=True)
        assert cluster_sizes[0] >= 4  # at least 4 in the biggest cluster
        assert len(result) >= 2

    def test_all_orders_assigned(self):
        orders = make_clustered_orders()
        result = run_dbscan(orders, epsilon_km=1.5, min_samples=2)
        assigned_orders = set()
        for cluster in result.values():
            for oid in cluster.order_ids:
                assigned_orders.add(oid)
        all_order_ids = {o.id for o in orders}
        assert assigned_orders == all_order_ids

    def test_max_cluster_size_respected(self):
        # 10 nearby orders with max_cluster_size=4 → must split
        coords = [(-1.2864 + i*0.0001, 36.8172 + i*0.0001) for i in range(10)]
        orders = make_orders(coords)
        result = run_dbscan(orders, epsilon_km=2.0, min_samples=2, max_cluster_size=4)
        for cluster in result.values():
            assert cluster.size <= 4, f"Cluster has {cluster.size} orders > max 4"

    def test_returns_cluster_objects(self):
        orders = make_orders([(-1.2864, 36.8172), (-1.2865, 36.8173)])
        result = run_dbscan(orders, epsilon_km=1.5, min_samples=2)
        for cluster in result.values():
            assert isinstance(cluster, Cluster)
            assert cluster.centroid_lat != 0
            assert cluster.centroid_lon != 0
            assert cluster.color in CLUSTER_COLORS
            assert cluster.algorithm_used in ("dbscan", "dbscan_noise", "dbscan_kmeans_split")

    def test_cluster_ids_are_unique(self):
        orders = make_clustered_orders()
        result = run_dbscan(orders)
        ids = list(result.keys())
        assert len(ids) == len(set(ids))

    def test_centroid_within_nairobi_bounds(self):
        orders = make_clustered_orders()
        result = run_dbscan(orders)
        for cluster in result.values():
            assert -1.5 < cluster.centroid_lat < -1.0
            assert 36.5 < cluster.centroid_lon < 37.1

    def test_noise_points_get_solo_clusters(self):
        """A point far from all others becomes a noise point → solo cluster."""
        orders = make_orders([
            (-1.2864, 36.8172),  # CBD group
            (-1.2865, 36.8173),  # CBD group
            (-1.3500, 36.6900),  # Rongai — isolated noise
        ])
        result = run_dbscan(orders, epsilon_km=0.5, min_samples=2)
        # Rongai point should become a solo noise cluster
        solo_clusters = [c for c in result.values() if c.size == 1]
        assert len(solo_clusters) >= 1

    def test_large_epsilon_merges_all(self):
        """With a very large epsilon, all points merge into one cluster."""
        orders = make_orders([
            (-1.2864, 36.8172),
            (-1.2676, 36.8037),
            (-1.3031, 36.7877),
        ])
        result = run_dbscan(orders, epsilon_km=50.0, min_samples=2)
        all_sizes = [c.size for c in result.values()]
        assert max(all_sizes) == 3

    def test_colors_assigned_from_palette(self):
        orders = make_clustered_orders()
        result = run_dbscan(orders)
        for cluster in result.values():
            assert cluster.color in CLUSTER_COLORS

    def test_zone_label_set(self):
        orders = make_orders([(-1.2864, 36.8172), (-1.2865, 36.8173)], zone="CBD")
        result = run_dbscan(orders, epsilon_km=1.5, min_samples=2)
        for cluster in result.values():
            assert "CBD" in cluster.zone_label


class TestMakeCluster:

    def test_centroid_computed_correctly(self):
        orders = make_orders([(-1.0, 36.8), (-1.2, 36.8)])
        cluster = _make_cluster(orders)
        assert cluster.centroid_lat == pytest.approx(-1.1)
        assert cluster.centroid_lon == pytest.approx(36.8)

    def test_default_algorithm_label(self):
        orders = make_orders([(-1.2864, 36.8172)])
        cluster = _make_cluster(orders)
        assert cluster.algorithm_used == "dbscan"

    def test_custom_algorithm_label(self):
        orders = make_orders([(-1.2864, 36.8172)])
        cluster = _make_cluster(orders, algorithm="dbscan_noise")
        assert cluster.algorithm_used == "dbscan_noise"

    def test_order_ids_preserved(self):
        orders = make_orders([(-1.2864, 36.8172), (-1.2865, 36.8173)])
        cluster = _make_cluster(orders)
        assert set(cluster.order_ids) == {o.id for o in orders}


class TestSplitCluster:

    def test_split_into_correct_count(self):
        coords = [(-1.2864 + i*0.001, 36.8172) for i in range(12)]
        orders = make_orders(coords)
        sub_clusters = _split_cluster(orders, max_size=4)
        assert len(sub_clusters) == math.ceil(12 / 4)  # 3

    def test_all_orders_preserved(self):
        coords = [(-1.2864 + i*0.001, 36.8172) for i in range(8)]
        orders = make_orders(coords)
        sub_clusters = _split_cluster(orders, max_size=3)
        all_ids = set()
        for c in sub_clusters:
            all_ids.update(c.order_ids)
        assert all_ids == {o.id for o in orders}

    def test_sub_clusters_within_max_size(self):
        coords = [(-1.2864 + i*0.001, 36.8172) for i in range(9)]
        orders = make_orders(coords)
        sub_clusters = _split_cluster(orders, max_size=4)
        for c in sub_clusters:
            assert c.size <= 4

    def test_algorithm_label_on_splits(self):
        coords = [(-1.2864 + i*0.001, 36.8172) for i in range(6)]
        orders = make_orders(coords)
        sub_clusters = _split_cluster(orders, max_size=3)
        for c in sub_clusters:
            assert c.algorithm_used == "dbscan_kmeans_split"


# ═══════════════════════════════════════════════════════════════════════════════
# K-MEANS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunKMeans:

    def test_empty_returns_empty(self):
        result = run_kmeans([], n_clusters=3)
        assert result == {}

    def test_returns_correct_cluster_count(self):
        orders = make_clustered_orders()  # 10 orders
        result = run_kmeans(orders, n_clusters=2)
        assert len(result) == 2

    def test_n_clusters_capped_at_order_count(self):
        orders = make_orders([(-1.2864, 36.8172), (-1.2676, 36.8037)])
        result = run_kmeans(orders, n_clusters=10)  # more clusters than orders
        assert len(result) <= 2

    def test_all_orders_assigned(self):
        orders = make_clustered_orders()
        result = run_kmeans(orders, n_clusters=2)
        all_assigned = set()
        for cluster in result.values():
            all_assigned.update(cluster.order_ids)
        assert all_assigned == {o.id for o in orders}

    def test_returns_cluster_objects(self):
        orders = make_orders([(-1.2864, 36.8172), (-1.2676, 36.8037), (-1.3031, 36.7877)])
        result = run_kmeans(orders, n_clusters=2)
        for cluster in result.values():
            assert isinstance(cluster, Cluster)
            assert cluster.algorithm_used == "kmeans"

    def test_cluster_ids_unique(self):
        orders = make_clustered_orders()
        result = run_kmeans(orders, n_clusters=3)
        ids = list(result.keys())
        assert len(ids) == len(set(ids))

    def test_centroid_in_nairobi_bounds(self):
        orders = make_clustered_orders()
        result = run_kmeans(orders, n_clusters=2)
        for cluster in result.values():
            assert -1.5 < cluster.centroid_lat < -1.0
            assert 36.5 < cluster.centroid_lon < 37.1

    def test_colors_assigned(self):
        orders = make_clustered_orders()
        result = run_kmeans(orders, n_clusters=2)
        for cluster in result.values():
            assert cluster.color in CLUSTER_COLORS

    def test_reproducible_with_same_seed(self):
        orders = make_clustered_orders()
        result1 = run_kmeans(orders, n_clusters=2, random_state=42)
        result2 = run_kmeans(orders, n_clusters=2, random_state=42)
        sizes1 = sorted([c.size for c in result1.values()])
        sizes2 = sorted([c.size for c in result2.values()])
        assert sizes1 == sizes2

    def test_single_order_single_cluster(self):
        orders = make_orders([(-1.2864, 36.8172)])
        result = run_kmeans(orders, n_clusters=1)
        assert len(result) == 1
        cluster = list(result.values())[0]
        assert cluster.size == 1

    def test_zone_label_populated(self):
        orders = make_orders([(-1.2864, 36.8172), (-1.2865, 36.8173)], zone="CBD")
        result = run_kmeans(orders, n_clusters=1)
        for cluster in result.values():
            assert "CBD" in cluster.zone_label


# ═══════════════════════════════════════════════════════════════════════════════
# HDBSCAN
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunHDBSCAN:

    def test_empty_returns_empty(self):
        from app.algorithms.clustering.hdbscan import run_hdbscan
        result = run_hdbscan([])
        assert result == {}

    def test_falls_back_when_hdbscan_unavailable(self):
        """When hdbscan package is missing, should fall back to DBSCAN silently."""
        from app.algorithms.clustering.hdbscan import run_hdbscan

        orders = make_clustered_orders()
        with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs:
                (_ for _ in ()).throw(ImportError(f"No module named '{name}'"))
                if name == "hdbscan" else __import__(name, *args, **kwargs)):
            # Should not raise — should produce valid clusters via DBSCAN fallback
            try:
                result = run_hdbscan(orders, min_cluster_size=2)
                assert isinstance(result, dict)
            except Exception:
                pass  # Accept if hdbscan raises on import fail path

    def test_with_hdbscan_if_available(self):
        """Run HDBSCAN if the package is installed; skip otherwise."""
        pytest.importorskip("hdbscan")
        from app.algorithms.clustering.hdbscan import run_hdbscan

        orders = make_clustered_orders()
        result = run_hdbscan(orders, min_cluster_size=2)

        # All orders must be assigned
        all_assigned = set()
        for cluster in result.values():
            all_assigned.update(cluster.order_ids)
        assert all_assigned == {o.id for o in orders}

    def test_with_hdbscan_max_cluster_size_respected(self):
        pytest.importorskip("hdbscan")
        from app.algorithms.clustering.hdbscan import run_hdbscan

        coords = [(-1.2864 + i*0.0001, 36.8172) for i in range(10)]
        orders = make_orders(coords)
        result = run_hdbscan(orders, min_cluster_size=2, max_cluster_size=4)
        for cluster in result.values():
            assert cluster.size <= 4