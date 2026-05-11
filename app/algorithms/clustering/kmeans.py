"""
app/algorithms/clustering/kmeans.py
─────────────────────────────────────────────────────────────────────────────
K-Means spatial clustering — alternative to DBSCAN.

When to use K-Means instead:
  - When driver count is known upfront (can set k = driver_count)
  - When order density is relatively uniform across the city
  - Faster than DBSCAN for large order sets

Limitation vs DBSCAN:
  - Must specify k (number of clusters) upfront
  - Sensitive to outliers (isolated orders distort centroids)
  - Always produces exactly k clusters even if some should merge
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
from loguru import logger
from sklearn.cluster import KMeans

from app.models.cluster import CLUSTER_COLORS, Cluster
from app.models.order import Order


def run_kmeans(
    orders: List[Order],
    n_clusters: int,
    random_state: int = 42,
) -> Dict[str, Cluster]:
    """
    Cluster orders using K-Means.

    Args:
        orders:       List of Order objects
        n_clusters:   Number of clusters (typically = driver count)
        random_state: Reproducibility seed

    Returns:
        Dict of cluster_id → Cluster
    """
    if not orders:
        return {}

    n_clusters = min(n_clusters, len(orders))
    coords = np.array([[o.lat, o.lon] for o in orders])

    km = KMeans(n_clusters=n_clusters, random_state=random_state, n_init="auto")
    labels = km.fit_predict(coords)

    logger.info(f"  KMeans: {n_clusters} clusters for {len(orders)} orders")

    clusters: Dict[str, Cluster] = {}
    color_idx = 0

    for k in range(n_clusters):
        cluster_orders = [o for o, l in zip(orders, labels) if l == k]
        if not cluster_orders:
            continue

        centroid_lat = float(np.mean([o.lat for o in cluster_orders]))
        centroid_lon = float(np.mean([o.lon for o in cluster_orders]))
        zones = [o.zone for o in cluster_orders]
        zone_label = f"{max(set(zones), key=zones.count)} cluster"

        cluster = Cluster(
            order_ids=[o.id for o in cluster_orders],
            centroid_lat=round(centroid_lat, 6),
            centroid_lon=round(centroid_lon, 6),
            color=CLUSTER_COLORS[color_idx % len(CLUSTER_COLORS)],
            zone_label=zone_label,
            algorithm_used="kmeans",
        )
        clusters[cluster.id] = cluster
        color_idx += 1

    return clusters