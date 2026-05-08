"""
app/algorithms/routing/dijkstra.py
─────────────────────────────────────────────────────────────────────────────
Dijkstra's algorithm on the Nairobi road graph via NetworkX.

Used when:
  - OSRM is unavailable (fallback)
  - We need shortest paths between specific road network nodes
  - Computing the full road-network distance matrix for OR-Tools input

Dijkstra is already implemented in NetworkX — this module wraps it with
Nairobi-specific context and the signature expected by routing_service.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import networkx as nx
from loguru import logger

from app.core.exceptions import GraphNotLoadedError


def shortest_path_between_nodes(
    G: nx.MultiDiGraph,
    source: int,
    target: int,
    weight: str = "length",
) -> Tuple[float, float, List[int]]:
    """
    Dijkstra shortest path between two road network nodes.

    Args:
        G:      Road network graph
        source: Source node ID
        target: Destination node ID
        weight: "length" (metres) or "travel_time" (seconds)

    Returns:
        (distance_km, travel_time_seconds, path_nodes)
    """
    try:
        path = nx.dijkstra_path(G, source, target, weight=weight)
        length_m = nx.dijkstra_path_length(G, source, target, weight="length")
        try:
            time_s = nx.dijkstra_path_length(G, source, target, weight="travel_time")
        except Exception:
            # travel_time may not be set if graph enrichment failed
            time_s = length_m / (30000 / 3600)  # assume 30 km/h

        return round(length_m / 1000, 4), round(time_s, 1), path

    except nx.NetworkXNoPath:
        logger.debug(f"  No path: {source} → {target}")
        return float("inf"), float("inf"), []
    except nx.NodeNotFound as exc:
        logger.warning(f"  Node not found: {exc}")
        return float("inf"), float("inf"), []


def multi_stop_shortest_path(
    G: nx.MultiDiGraph,
    node_sequence: List[int],
    weight: str = "length",
) -> Tuple[float, float, List[int]]:
    """
    Compute the total shortest path for an ordered sequence of stops.

    Args:
        G:             Road graph
        node_sequence: Ordered list of node IDs to visit
        weight:        Edge weight attribute

    Returns:
        (total_distance_km, total_time_seconds, full_path_nodes)
    """
    if len(node_sequence) < 2:
        return 0.0, 0.0, node_sequence

    total_dist = 0.0
    total_time = 0.0
    full_path: List[int] = [node_sequence[0]]

    for i in range(len(node_sequence) - 1):
        dist, time, segment = shortest_path_between_nodes(
            G, node_sequence[i], node_sequence[i + 1], weight=weight
        )
        if dist == float("inf"):
            # Skip unreachable segments
            full_path.append(node_sequence[i + 1])
            continue
        total_dist += dist
        total_time += time
        # Avoid duplicate nodes at segment boundaries
        full_path.extend(segment[1:])

    return round(total_dist, 4), round(total_time, 1), full_path