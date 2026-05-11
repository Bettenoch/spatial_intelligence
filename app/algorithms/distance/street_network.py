"""
app/algorithms/distance/street_network.py
─────────────────────────────────────────────────────────────────────────────
Street-network distance calculation using the loaded OSMnx graph.

Uses NetworkX shortest-path algorithms (Dijkstra under the hood) on the
Nairobi road graph.  Returns actual road distances and travel times.

Educational note:
  - Road distance is typically 1.3–1.8× the straight-line Haversine distance
  - This ratio (circuity factor) varies by city layout and traffic patterns
  - Nairobi's circuity is high in CBD (~1.5×) due to one-way streets
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import networkx as nx
from loguru import logger


def shortest_path_distance(
    G: nx.MultiDiGraph,
    origin_node: int,
    dest_node: int,
    weight: str = "travel_time",
) -> Tuple[float, float, List[int]]:
    """
    Compute shortest path between two road network nodes.

    Args:
        G:            Nairobi road graph
        origin_node:  Source node ID
        dest_node:    Destination node ID
        weight:       Edge attribute to minimise ("travel_time" or "length")

    Returns:
        (distance_km, duration_seconds, path_node_list)
        Returns (inf, inf, []) if no path exists.
    """
    try:
        path = nx.shortest_path(G, origin_node, dest_node, weight=weight)
        length_m = nx.shortest_path_length(G, origin_node, dest_node, weight="length")
        time_s = nx.shortest_path_length(G, origin_node, dest_node, weight="travel_time")
        return round(length_m / 1000, 4), round(time_s, 1), path
    except nx.NetworkXNoPath:
        return float("inf"), float("inf"), []
    except nx.NodeNotFound:
        return float("inf"), float("inf"), []


def path_to_geojson_coordinates(
    G: nx.MultiDiGraph,
    path: List[int],
) -> List[List[float]]:
    """
    Convert a list of road graph node IDs to GeoJSON [lon, lat] coordinates.

    For each edge in the path, extracts the 'geometry' attribute if it exists
    (it does when OSMnx has stored the actual road curve) or interpolates
    a straight line between nodes.
    """
    from shapely.geometry import LineString

    coords: List[List[float]] = []

    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        # Get the edge data (use first parallel edge)
        edge_data = G.get_edge_data(u, v)
        if not edge_data:
            # Fallback to node coordinates
            n = G.nodes[u]
            coords.append([n["x"], n["y"]])
            continue

        # edge_data is a dict keyed by edge key (0, 1, …)
        first_edge = edge_data[min(edge_data.keys())]
        
        if "geometry" in first_edge:
            geom: LineString = first_edge["geometry"]
            for lon, lat in geom.coords:
                coords.append([lon, lat])
        else:
            n1 = G.nodes[u]
            coords.append([n1["x"], n1["y"]])

    # Add the final destination node
    if path:
        last_node = G.nodes[path[-1]]
        coords.append([last_node["x"], last_node["y"]])

    return coords


def build_street_network_geojson(
    G: nx.MultiDiGraph,
    full_path_nodes: List[int],
    method: str = "street_network",
) -> dict:
    """
    Build a GeoJSON Feature from a sequence of road graph nodes.

    Args:
        G:                The Nairobi road graph
        full_path_nodes:  Concatenated list of node IDs from the full tour
        method:           Routing method label for the properties field

    Returns:
        GeoJSON Feature with LineString geometry.
    """
    coordinates = path_to_geojson_coordinates(G, full_path_nodes)

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
        "properties": {
            "method": method,
            "node_count": len(full_path_nodes),
        },
    }


def street_distance_matrix(
    G: nx.MultiDiGraph,
    node_ids: List[int],
    weight: str = "length",
) -> Tuple[list, list]:
    """
    Compute NxN distance and time matrices for a set of road nodes.

    Returns:
        (distance_matrix_km, time_matrix_seconds)
        Both are N×N Python lists.
    """
    n = len(node_ids)
    dist_km = [[0.0] * n for _ in range(n)]
    time_s = [[0.0] * n for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            km, sec, _ = shortest_path_distance(G, node_ids[i], node_ids[j])
            dist_km[i][j] = km if km != float("inf") else 999.0
            time_s[i][j] = sec if sec != float("inf") else 99999.0

    return dist_km, time_s