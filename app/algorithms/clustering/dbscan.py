"""
app/algorithms/clustering/dbscan.py
─────────────────────────────────────────────────────────────────────────────
DBSCAN (Density-Based Spatial Clustering of Applications with Noise)
applied to GPS coordinates for order batching.

Why DBSCAN for delivery routing:
  - No need to specify number of clusters upfront (unlike K-Means)
  - Handles arbitrary cluster shapes (Nairobi roads aren't grid-like)
  - Identifies noise points (isolated orders) — these become solo trips
  - Works perfectly with GPS coordinates converted to metres

Implementation note:
  We project lat/lon to UTM Zone 37S (the correct UTM zone for Nairobi)
  before running DBSCAN.  This gives us accurate metre-based distances.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
from loguru import logger
from sklearn.cluster import DBSCAN

from app.models.cluster import CLUSTER_COLORS, Cluster
from app.models.order import Order


def _project_to_metres(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """
    Project WGS84 lat/lon to UTM Zone 37S (EPSG:32737) in metres.

    Args:
        lats: 1D array of latitudes
        lons: 1D array of longitudes

    Returns:
        (N, 2) array of [easting, northing] in metres
    """
    from pyproj import Transformer
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32737", always_xy=True)
    xs, ys = transformer.transform(lons, lats)
    return np.column_stack([xs, ys])


def run_dbscan(
    orders: List[Order],
    epsilon_km: float = 1.5,
    min_samples: int = 2,
    max_cluster_size: int = 6,
) -> Dict[str, Cluster]:
    """
    Cluster a list of orders using DBSCAN.

    Args:
        orders:           List of Order objects (must have lat/lon)
        epsilon_km:       Max distance between points in the same cluster (km)
        min_samples:      Minimum orders to form a dense cluster
        max_cluster_size: Cluster exceeding this size gets split

    Returns:
        Dict of cluster_id → Cluster
    """
    if not orders:
        return {}

    lats = np.array([o.lat for o in orders])
    lons = np.array([o.lon for o in orders])

    # Project to metres for accurate distance computation
    coords_m = _project_to_metres(lats, lons)

    # DBSCAN — epsilon in metres, metric='euclidean' on projected coords
    epsilon_m = epsilon_km * 1000
    db = DBSCAN(eps=epsilon_m, min_samples=min_samples, metric="euclidean", n_jobs=-1)
    labels = db.fit_predict(coords_m)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = np.sum(labels == -1)
    logger.info(
        f"  DBSCAN: {n_clusters} clusters, {n_noise} noise/solo orders "
        f"(ε={epsilon_km}km, min_samples={min_samples})"
    )

    clusters: Dict[str, Cluster] = {}
    color_idx = 0

    # Group orders by DBSCAN label
    label_to_orders: Dict[int, List[Order]] = {}
    for order, label in zip(orders, labels):
        label_to_orders.setdefault(int(label), []).append(order)

    for label, cluster_orders in label_to_orders.items():
        if label == -1:
            # Noise points — each becomes its own single-order cluster
            for order in cluster_orders:
                cluster = _make_cluster(
                    [order],
                    color=CLUSTER_COLORS[color_idx % len(CLUSTER_COLORS)],
                    algorithm="dbscan_noise",
                )
                clusters[cluster.id] = cluster
                color_idx += 1
        else:
            # Dense cluster — may need splitting if too large
            if len(cluster_orders) <= max_cluster_size:
                cluster = _make_cluster(
                    cluster_orders,
                    color=CLUSTER_COLORS[color_idx % len(CLUSTER_COLORS)],
                    algorithm="dbscan",
                )
                clusters[cluster.id] = cluster
                color_idx += 1
            else:
                # Split oversized cluster
                sub_clusters = _split_cluster(cluster_orders, max_cluster_size)
                for sub in sub_clusters:
                    sub.color = CLUSTER_COLORS[color_idx % len(CLUSTER_COLORS)]
                    clusters[sub.id] = sub
                    color_idx += 1

    logger.info(f"  Final: {len(clusters)} clusters (after noise expansion + splitting)")
    return clusters


def _make_cluster(
    orders: List[Order],
    color: str = "#FF6B35",
    algorithm: str = "dbscan",
) -> Cluster:
    """Create a Cluster object from a list of orders."""
    centroid_lat = float(np.mean([o.lat for o in orders]))
    centroid_lon = float(np.mean([o.lon for o in orders]))

    # Label by dominant zone
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
    """
    Split an oversized cluster into sub-clusters using KMeans.
    Called when DBSCAN produces a cluster larger than driver capacity.
    """
    from sklearn.cluster import KMeans

    n_sub = math.ceil(len(orders) / max_size)
    coords = np.array([[o.lat, o.lon] for o in orders])
    km = KMeans(n_clusters=n_sub, random_state=42, n_init="auto")
    labels = km.fit_predict(coords)

    sub_clusters = []
    for label in range(n_sub):
        sub_orders = [o for o, l in zip(orders, labels) if l == label]
        if sub_orders:
            sub_clusters.append(_make_cluster(sub_orders, algorithm="dbscan_kmeans_split"))
    return sub_clusters


import math  # noqa: E402  (placed here to avoid circular at module level)