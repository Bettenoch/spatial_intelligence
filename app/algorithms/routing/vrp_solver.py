"""
app/algorithms/routing/vrp_solver.py
─────────────────────────────────────────────────────────────────────────────
Vehicle Routing Problem (VRP) solver using Google OR-Tools.

The VRP is the core optimisation problem in delivery logistics:
Given N orders and K drivers, find the minimum-cost assignment and
route ordering such that:
  - Each order is delivered exactly once
  - Each driver's capacity is not exceeded
  - Total travel distance is minimised

OR-Tools uses metaheuristic search (guided local search + simulated
annealing) to find near-optimal solutions in milliseconds.

This is the algorithm that runs when method = STREET_NETWORK.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from loguru import logger


def solve_vrp(
    distance_matrix: List[List[float]],
    driver_count: int,
    demands: Optional[List[int]] = None,
    capacity: int = 6,
    max_distance_km: float = 50.0,
    time_limit_seconds: int = 5,
) -> Optional[List[List[int]]]:
    """
    Solve Vehicle Routing Problem using Google OR-Tools.

    Args:
        distance_matrix:  NxN matrix of distances (km).
                          Index 0 is the depot (driver start).
                          Indices 1..N are delivery stops.
        driver_count:     Number of available drivers (vehicles).
        demands:          Demand per stop (default: 1 per delivery stop).
        capacity:         Max demand per driver.
        max_distance_km:  Max km per driver route.
        time_limit_seconds: Solver time budget.

    Returns:
        List of routes, where each route is a list of node indices.
        Returns None if OR-Tools is unavailable (falls back to greedy).
    """
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError:
        logger.warning("  OR-Tools not installed — using greedy nearest-neighbour fallback")
        return _greedy_vrp_fallback(distance_matrix, driver_count, capacity)

    n_locations = len(distance_matrix)
    if n_locations <= 1:
        return [[0]]

    # OR-Tools works with integers — scale km * 1000 to avoid float issues
    def dist_callback(from_idx: int, to_idx: int) -> int:
        from_node = manager.IndexToNode(from_idx)
        to_node = manager.IndexToNode(to_idx)
        return int(distance_matrix[from_node][to_node] * 1000)

    def demand_callback(from_idx: int) -> int:
        node = manager.IndexToNode(from_idx)
        return 0 if node == 0 else (demands[node] if demands else 1)

    manager = pywrapcp.RoutingIndexManager(n_locations, driver_count, 0)
    routing = pywrapcp.RoutingModel(manager)

    # Distance callback
    transit_cb_idx = routing.RegisterTransitCallback(dist_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb_idx)

    # Capacity constraint
    demand_cb_idx = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_cb_idx,
        0,
        [capacity] * driver_count,
        True,
        "Capacity",
    )

    # Max distance per vehicle
    routing.AddDimension(
        transit_cb_idx,
        0,
        int(max_distance_km * 1000),
        True,
        "Distance",
    )

    # Search parameters
    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_params.time_limit.seconds = time_limit_seconds

    solution = routing.SolveWithParameters(search_params)

    if not solution:
        logger.warning("  OR-Tools found no solution — using greedy fallback")
        return _greedy_vrp_fallback(distance_matrix, driver_count, capacity)

    routes: List[List[int]] = []
    for vehicle_id in range(driver_count):
        index = routing.Start(vehicle_id)
        route: List[int] = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            route.append(node)
            index = solution.Value(routing.NextVar(index))
        route.append(manager.IndexToNode(index))  # back to depot
        if len(route) > 2:  # has at least one delivery stop
            routes.append(route)

    total_dist = sum(
        distance_matrix[r[i]][r[i+1]]
        for r in routes
        for i in range(len(r)-1)
    )
    logger.info(
        f"  OR-Tools VRP: {len(routes)} routes, "
        f"total distance={total_dist:.1f}km"
    )
    return routes


def _greedy_vrp_fallback(
    distance_matrix: List[List[float]],
    driver_count: int,
    capacity: int,
) -> List[List[int]]:
    """
    Simple greedy nearest-neighbour VRP fallback when OR-Tools unavailable.
    Used as a safety net — not the primary solver.
    """
    n = len(distance_matrix)
    stops = list(range(1, n))  # indices 1..N are delivery stops
    routes: List[List[int]] = []

    for _ in range(driver_count):
        if not stops:
            break
        route = [0]  # start at depot
        load = 0

        while stops and load < capacity:
            current = route[-1]
            nearest = min(stops, key=lambda j: distance_matrix[current][j])
            route.append(nearest)
            stops.remove(nearest)
            load += 1

        route.append(0)  # return to depot
        if len(route) > 2:
            routes.append(route)

    return routes