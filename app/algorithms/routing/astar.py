"""
app/algorithms/routing/astar.py
─────────────────────────────────────────────────────────────────────────────
A* (A-star) shortest path on the Nairobi road graph via NetworkX.

A* improves on Dijkstra by using a heuristic — the straight-line (Haversine)
distance to the goal — to guide the search toward the target.  This makes
it significantly faster than Dijkstra for single source→destination queries
on large graphs like the full Nairobi network.

When to use A* instead of Dijkstra:
  - Single origin → single destination (not all-pairs)
  - Graph is large (Nairobi: ~50k nodes)
  - Coordinates are available on nodes (osmnx always stores x/y)

The heuristic MUST be admissible (never overestimates the true cost) and
consistent.  Haversine distance satisfies both properties when edge weights
are in metres.

Architecture note:
  This module is pure algorithm — no API or service logic here.
  routing_service.py decides when to call A* vs Dijkstra vs OSRM.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import math
from typing import List, Tuple

import networkx as nx
from loguru import logger


def _haversine_heuristic(u: int, v: int, G: nx.MultiDiGraph) -> float:
    """
    Haversine distance (metres) between two nodes — used as the A* heuristic.

    NetworkX A* calls heuristic(u, v) where u is a candidate node and v is
    the target node.  We close over the graph G to access node coordinates.
    """
    u_data = G.nodes[u]
    v_data = G.nodes[v]

    lat1, lon1 = math.radians(u_data["y"]), math.radians(u_data["x"])
    lat2, lon2 = math.radians(v_data["y"]), math.radians(v_data["x"])

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return 6_371_000 * c  # metres


def astar_path(
    G: nx.MultiDiGraph,
    source: int,
    target: int,
    weight: str = "length",
) -> Tuple[float, float, List[int]]:
    """
    A* shortest path between two road network nodes.

    Args:
        G:      Nairobi road graph (nodes must have x/y attributes)
        source: Origin node ID
        target: Destination node ID
        weight: Edge attribute to minimise ("length" in metres or "travel_time")

    Returns:
        (distance_km, travel_time_seconds, path_node_list)
        Returns (inf, inf, []) when no path exists.
    """
    # Build a heuristic that closes over G
    def heuristic(u: int, v: int) -> float:
        return _haversine_heuristic(u, v, G)

    try:
        path: List[int] = nx.astar_path(G, source, target, heuristic=heuristic, weight=weight)

        length_m = nx.astar_path_length(G, source, target, heuristic=heuristic, weight="length")
        try:
            time_s = nx.astar_path_length(G, source, target, heuristic=heuristic, weight="travel_time")
        except Exception:
            time_s = length_m / (30_000 / 3600)  # fallback: 30 km/h

        return round(length_m / 1000, 4), round(time_s, 1), path

    except nx.NetworkXNoPath:
        logger.debug(f"  A*: no path {source} → {target}")
        return float("inf"), float("inf"), []
    except nx.NodeNotFound as exc:
        logger.warning(f"  A*: node not found — {exc}")
        return float("inf"), float("inf"), []


def multi_stop_astar(
    G: nx.MultiDiGraph,
    node_sequence: List[int],
    weight: str = "length",
) -> Tuple[float, float, List[int]]:
    """
    Total A* path through an ordered sequence of stops.

    Args:
        G:             Road graph
        node_sequence: Ordered list of node IDs to visit
        weight:        Edge weight attribute

    Returns:
        (total_distance_km, total_time_seconds, full_path_nodes)
    """
    if len(node_sequence) < 2:
        return 0.0, 0.0, list(node_sequence)

    total_dist = 0.0
    total_time = 0.0
    full_path: List[int] = [node_sequence[0]]

    for i in range(len(node_sequence) - 1):
        dist, time, segment = astar_path(G, node_sequence[i], node_sequence[i + 1], weight=weight)
        if dist == float("inf"):
            full_path.append(node_sequence[i + 1])
            continue
        total_dist += dist
        total_time += time
        full_path.extend(segment[1:])  # skip duplicate boundary node

    return round(total_dist, 4), round(total_time, 1), full_path