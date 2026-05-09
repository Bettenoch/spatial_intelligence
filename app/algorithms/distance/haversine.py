"""
app/algorithms/distance/haversine.py
─────────────────────────────────────────────────────────────────────────────
Haversine formula — accurate great-circle distance on Earth's surface.

Formula:
  a = sin²(Δφ/2) + cos φ₁ · cos φ₂ · sin²(Δλ/2)
  c = 2 · atan2(√a, √(1−a))
  d = R · c     where R = 6371 km

Advantages over Euclidean:
  - Accounts for Earth's curvature
  - Accurate for any distance on Earth
  - Still assumes as-the-crow-flies (ignores roads)

Educational note for the learning panel:
  - Difference from Euclidean is <0.5% for distances <50km
  - For Nairobi intra-city routing (1–20km) the correction is small
  - Matters more for long-haul logistics (Nairobi→Mombasa)
  - Still draws straight lines — not real roads
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np

EARTH_RADIUS_KM = 6371.0


def haversine_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """
    Great-circle distance between two GPS points using the Haversine formula.

    Args:
        lat1, lon1: Origin coordinates in decimal degrees
        lat2, lon2: Destination coordinates in decimal degrees

    Returns:
        Distance in kilometres.
    """
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)

    a = (
        math.sin(Δφ / 2) ** 2
        + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def haversine_distance_matrix(coords: np.ndarray) -> np.ndarray:
    """
    Full NxN Haversine distance matrix.

    Args:
        coords: (N, 2) array of [lat, lon] in degrees

    Returns:
        NxN distance matrix in kilometres.
    """
    n = len(coords)
    matrix = np.zeros((n, n))

    for i in range(n):
        for j in range(i + 1, n):
            d = haversine_distance(
                coords[i, 0], coords[i, 1],
                coords[j, 0], coords[j, 1],
            )
            matrix[i, j] = d
            matrix[j, i] = d

    return matrix


def nearest_neighbour_tour_haversine(
    coords: np.ndarray,
    start_idx: int = 0,
) -> Tuple[List[int], float]:
    """
    Nearest-neighbour TSP heuristic using Haversine distances.

    Args:
        coords:    (N, 2) array of [lat, lon]
        start_idx: Starting point index

    Returns:
        (ordered_indices, total_distance_km)
    """
    n = len(coords)
    if n == 0:
        return [], 0.0
    if n == 1:
        return [0], 0.0

    dist_matrix = haversine_distance_matrix(coords)
    visited = [False] * n
    tour = [start_idx]
    visited[start_idx] = True
    total_dist = 0.0

    current = start_idx
    for _ in range(n - 1):
        best_dist = float("inf")
        best_next = -1
        for j in range(n):
            if not visited[j] and dist_matrix[current, j] < best_dist:
                best_dist = dist_matrix[current, j]
                best_next = j
        tour.append(best_next)
        visited[best_next] = True
        total_dist += best_dist
        current = best_next

    # Return to start
    total_dist += dist_matrix[current, start_idx]

    return tour, total_dist


def build_haversine_geojson(
    coords: np.ndarray,
    tour: List[int],
) -> dict:
    """
    Build a GeoJSON LineString for the Haversine tour.
    For short distances the line looks identical to Euclidean on the map.
    """
    line_coords = [[float(coords[i, 1]), float(coords[i, 0])] for i in tour]
    if tour:
        line_coords.append([float(coords[tour[0], 1]), float(coords[tour[0], 0])])

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": line_coords,
        },
        "properties": {
            "method": "haversine",
        },
    }


def total_route_distance(ordered_coords: List[Tuple[float, float]]) -> float:
    """
    Calculate total Haversine distance for an ordered list of (lat, lon) waypoints.

    Args:
        ordered_coords: List of (lat, lon) in visit order

    Returns:
        Total route distance in kilometres.
    """
    total = 0.0
    for i in range(len(ordered_coords) - 1):
        total += haversine_distance(
            ordered_coords[i][0], ordered_coords[i][1],
            ordered_coords[i + 1][0], ordered_coords[i + 1][1],
        )
    return total