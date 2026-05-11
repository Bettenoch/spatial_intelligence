"""
app/algorithms/clustering/hdbscan.py
─────────────────────────────────────────────────────────────────────────────
HDBSCAN (Hierarchical DBSCAN) — advanced spatial clustering.

Advantages over DBSCAN:
  - Robust to varying density (Nairobi CBD is denser than Rongai)
  - No epsilon parameter — cluster scale is inferred from data
  - Produces a soft membership probability per point
  - Better at detecting clusters of very different sizes

Dependency: hdbscan package (separate from sklearn — install explicitly)
    pip install hdbscan

Falls back to DBSCAN if hdbscan is not installed, so the backend never
fails if the package is missing.

Architecture note:
  Pure algorithm module — no API or service logic.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import math
from typing import Dict, List

import numpy as np
from loguru import logger

from app.models.cluster import CLUSTER_COLORS, Cluster
from app.models.order import Order


def _project_to_metres(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Project WGS84 to UTM Zone 37S (EPSG:32737) in metres."""
    from pyproj import Transformer
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32737", always_xy=True)
    xs, ys = transformer.transform(lons, lats)
    return np.column_stack([xs, ys])


def run_hdbscan(
    orders: List[Order],
    min_cluster_size: int = 2,
    min_samples: int = 1,
    max_cluster_size: int = 6,
) -> Dict[str, Cluster]:
    """
    Cluster orders using HDBSCAN.

    Args:
        orders:           List of Order objects (must have lat/lon)
        min_cluster_size: Smallest grouping considered a cluster (default 2)
        min_samples:      Controls how conservative clustering is (default 1)
        max_cluster_size: Clusters larger than this are split via KMeans

    Returns:
        Dict of cluster_id → Cluster

    Falls back to DBSCAN if hdbscan package is not installed.
    """
    if not orders:
        return {}

    try:
        import hdbscan as hdbscan_lib
    except ImportError:
        logger.warning(
            "  hdbscan package not installed — falling back to DBSCAN. "
            "Install with: pip install hdbscan"
        )
        from app.algorithms.clustering.dbscan import run_dbscan
        return run_dbscan(orders, min_samples=min_cluster_size, max_cluster_size=max_cluster_size)

    lats = np.array([o.lat for o in orders])
    lons = np.array([o.lon for o in orders])
    coords_m = _project_to_metres(lats, lons)

    clusterer = hdbscan_lib.HDBSCAN( # type: ignore
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",  # excess of mass — finds compact clusters
    )
    labels = clusterer.fit_predict(coords_m)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int(np.sum(labels == -1))
    logger.info(
        f"  HDBSCAN: {n_clusters} clusters, {n_noise} noise/solo orders "
        f"(min_cluster_size={min_cluster_size})"
    )

    clusters: Dict[str, Cluster] = {}
    color_idx = 0

    label_to_orders: Dict[int, List[Order]] = {}
    for order, label in zip(orders, labels):
        label_to_orders.setdefault(int(label), []).append(order)

    for label, cluster_orders in label_to_orders.items():
        if label == -1:
            # Noise — each order gets its own solo cluster
            for order in cluster_orders:
                cluster = _make_cluster(
                    [order],
                    color=CLUSTER_COLORS[color_idx % len(CLUSTER_COLORS)],
                    algorithm="hdbscan_noise",
                )
                clusters[cluster.id] = cluster
                color_idx += 1
        elif len(cluster_orders) <= max_cluster_size:
            cluster = _make_cluster(
                cluster_orders,
                color=CLUSTER_COLORS[color_idx % len(CLUSTER_COLORS)],
                algorithm="hdbscan",
            )
            clusters[cluster.id] = cluster
            color_idx += 1
        else:
            sub_clusters = _split_cluster(cluster_orders, max_cluster_size)
            for sub in sub_clusters:
                sub.color = CLUSTER_COLORS[color_idx % len(CLUSTER_COLORS)]
                clusters[sub.id] = sub
                color_idx += 1

    logger.info(f"  Final: {len(clusters)} clusters")
    return clusters


def _make_cluster(
    orders: List[Order],
    color: str = "#FF6B35",
    algorithm: str = "hdbscan",
) -> Cluster:
    centroid_lat = float(np.mean([o.lat for o in orders]))
    centroid_lon = float(np.mean([o.lon for o in orders]))
    zones = [o.zone for o in orders]
    zone_label = f"{max(set(zones), key=zones.count)} cluster"
    return Cluster(
        order_ids=[o.id for o in orders],
        centroid_lat=round(centroid_lat, 6),
        centroid_lon=round(centroid_lon, 6),
        color=color,
        zone_label=zone_label,
        algorithm_used=algorithm,
    )


def _split_cluster(orders: List[Order], max_size: int) -> List[Cluster]:
    from sklearn.cluster import KMeans
    n_sub = math.ceil(len(orders) / max_size)
    coords = np.array([[o.lat, o.lon] for o in orders])
    km = KMeans(n_clusters=n_sub, random_state=42, n_init="auto")
    labels = km.fit_predict(coords)
    sub_clusters = []
    for lbl in range(n_sub):
        sub_orders = [o for o, l in zip(orders, labels) if l == lbl]
        if sub_orders:
            sub_clusters.append(_make_cluster(sub_orders, algorithm="hdbscan_kmeans_split"))
    return sub_clusters