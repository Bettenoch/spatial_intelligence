"""
tests/conftest.py
─────────────────────────────────────────────────────────────────────────────
Shared pytest fixtures used across all test modules.

Provides:
  - Sample orders/drivers/clusters for unit tests (no graph required)
  - A mock graph_loader so spatial tests don't need the real OSMnx graph
  - A FastAPI TestClient wired up for API/WebSocket tests
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ── Make sure the project root is importable ─────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── Nairobi coordinate helpers ────────────────────────────────────────────────

NAIROBI_CBD = (-1.2864, 36.8172)
NAIROBI_WESTLANDS = (-1.2676, 36.8037)
NAIROBI_KILIMANI = (-1.3031, 36.7877)
NAIROBI_KAREN = (-1.2996, 36.7500)
NAIROBI_KASARANI = (-1.2195, 36.8876)


# ── Model fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def sample_orders():
    """10 orders spread across Nairobi zones — no graph required."""
    from app.models.order import Order, OrderType

    coords = [
        (-1.2864, 36.8172, "CBD"),
        (-1.2870, 36.8180, "CBD"),
        (-1.2855, 36.8165, "CBD"),
        (-1.2676, 36.8037, "Westlands"),
        (-1.2680, 36.8045, "Westlands"),
        (-1.3031, 36.7877, "Kilimani"),
        (-1.3025, 36.7885, "Kilimani"),
        (-1.2996, 36.7500, "Karen"),
        (-1.2195, 36.8876, "Kasarani"),
        (-1.3500, 36.6900, "Rongai"),
    ]
    return [
        Order(lat=lat, lon=lon, zone=zone, order_type=OrderType.FOOD)
        for lat, lon, zone in coords
    ]


@pytest.fixture
def sample_drivers():
    """3 drivers positioned around Nairobi."""
    from app.models.driver import Driver

    return [
        Driver(name="Brian K.", lat=-1.2864, lon=36.8172, zone="CBD"),
        Driver(name="Wanjiru M.", lat=-1.2676, lon=36.8037, zone="Westlands"),
        Driver(name="Otieno D.", lat=-1.3031, lon=36.7877, zone="Kilimani"),
    ]


@pytest.fixture
def sample_cluster(sample_orders):
    """A single cluster containing the first 3 orders (all CBD)."""
    from app.models.cluster import Cluster

    cbd_orders = sample_orders[:3]
    return Cluster(
        order_ids=[o.id for o in cbd_orders],
        centroid_lat=-1.2863,
        centroid_lon=36.8172,
        zone_label="CBD cluster",
    )


@pytest.fixture
def sample_simulation_state(sample_orders, sample_drivers):
    """Minimal SimulationState with orders + drivers, no routes/clusters."""
    from app.models.simulation import SimulationConfig, SimulationState, SimulationStatus
    from app.models.route import RoutingMethod

    config = SimulationConfig(order_count=10, driver_count=3, routing_method=RoutingMethod.HAVERSINE)
    state = SimulationState(config=config)
    state.orders = {o.id: o for o in sample_orders}
    state.drivers = {d.id: d for d in sample_drivers}
    state.metrics.deliveries_total = len(sample_orders)
    state.metrics.active_drivers = len(sample_drivers)
    return state


# ── Mock graph loader ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_graph_loader():
    """
    Returns a patched graph_loader that reports is_ready=True
    but never touches the real OSMnx cache.
    """
    mock_loader = MagicMock()
    mock_loader.is_ready.return_value = True
    mock_loader.nearest_node.return_value = (123456789, 12.5)  # (node_id, dist_m)
    mock_loader.get_graph.return_value = MagicMock()
    mock_loader.stats.return_value = {
        "ready": True, "node_count": 50000, "edge_count": 120000, "load_time_seconds": 3.1
    }
    return mock_loader


@pytest.fixture
def mock_graph_not_ready():
    """graph_loader that reports not ready (simulates cold start)."""
    mock_loader = MagicMock()
    mock_loader.is_ready.return_value = False
    return mock_loader


# ── FastAPI test client ───────────────────────────────────────────────────────

@pytest.fixture
def client(mock_graph_loader):
    """
    TestClient with graph_loader mocked so the app doesn't download OSMnx
    during tests.
    """
    from fastapi.testclient import TestClient

    with patch("app.core.graph_loader.graph_loader", mock_graph_loader):
        with patch("app.api.routes.simulation.graph_loader", mock_graph_loader):
            from app.main import app
            yield TestClient(app)


# ── Coordinate array helpers ──────────────────────────────────────────────────

@pytest.fixture
def cbd_coords():
    """Small tight cluster of CBD coordinates as numpy array."""
    return np.array([
        [-1.2864, 36.8172],
        [-1.2870, 36.8180],
        [-1.2855, 36.8165],
        [-1.2860, 36.8175],
    ])


@pytest.fixture
def spread_coords():
    """Coordinates spread across different Nairobi zones."""
    return np.array([
        [-1.2864, 36.8172],   # CBD
        [-1.2676, 36.8037],   # Westlands
        [-1.3031, 36.7877],   # Kilimani
        [-1.2996, 36.7500],   # Karen
        [-1.2195, 36.8876],   # Kasarani
    ])