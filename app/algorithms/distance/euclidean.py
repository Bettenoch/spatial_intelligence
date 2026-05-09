"""
app/lgorithms/distance/euclidean.py
─────────────────────────────────────────────────────────────────────────────
Euclidean (straight-line) distance calculator.

Formula:  d = √((x₂-x₁)² + (y₂-y₁)²)

Treats lat/lon as flat Cartesian coordinates — fast but only accurate for
very short distances in the same locale.  Used as the "naive baseline" mode
to visually demonstrate why naive routing is insufficient.

Educational note for the learning panel:
  - Ignores Earth's curvature entirely
  - Overestimates distance near the equator (Nairobi is ~1.3° S)
  - Suitable for micro-distances (<500m) or illustrative purposes
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np


def euclidean_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """
    Straight-line distance between two GPS points, treating
    lat/lon as flat Cartesian coordinates.

    Returns:
        Approximate distance in kilometres (rough — not Earth-corrected).
    """
    # 1 degree of latitude ≈ 111 km
    # 1 degree of longitude ≈ 111 * cos(lat) km  (ignored here — Euclidean)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    # Convert degrees to km (rough approximation)
    d_km = math.sqrt(dlat**2 + dlon**2) * 111.0
    return d_km


def euclidean_distance_matrix(
    coords: np.ndarray,
) -> np.ndarray:
    """
    Compute the full NxN Euclidean distance matrix for a set of coordinates.

    Args:
        coords: Numpy array of shape (N, 2) where columns are [lat, lon]

    Returns:
        NxN distance matrix in kilometres.
    """
    n = len(coords)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = euclidean_distance(
                coords[i, 0], coords[i, 1],
                coords[j, 0], coords[j, 1],
            )
            matrix[i, j] = d
            matrix[j, i] = d
    return matrix


def nearest_neighbour_tour(
    coords: np.ndarray,
    start_idx: int = 0,
) -> Tuple[List[int], float]:
    """
    Greedy nearest-neighbour TSP heuristic using Euclidean distances.

    Args:
        coords:     (N, 2) array of [lat, lon]
        start_idx:  Index of the starting point (driver location)

    Returns:
        (ordered_indices, total_distance_km)
    """
    n = len(coords)
    if n == 0:
        return [], 0.0
    if n == 1:
        return [0], 0.0

    dist_matrix = euclidean_distance_matrix(coords)
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

    # Return to start (closed tour)
    total_dist += dist_matrix[current, start_idx]

    return tour, total_dist


def build_euclidean_geojson(
    coords: np.ndarray,
    tour: List[int],
) -> dict:
    """
    Build a GeoJSON LineString from a tour and coordinate array.

    Args:
        coords: (N, 2) [lat, lon] array — all points including driver
        tour:   Ordered list of indices into coords

    Returns:
        GeoJSON LineString dict.
    """
    # GeoJSON uses [lon, lat] order
    line_coords = [[float(coords[i, 1]), float(coords[i, 0])] for i in tour]
    # Close the loop back to start
    if tour:
        line_coords.append([float(coords[tour[0], 1]), float(coords[tour[0], 0])])

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": line_coords,
        },
        "properties": {
            "method": "euclidean",
        },
    }