"""
app/core/exceptions.py
─────────────────────────────────────────────────────────────────────────────
Custom exception classes for the Nairobi Routing Backend.

Design principle: every exception maps cleanly to an HTTP status code and
carries a human-readable message that can be surfaced to the frontend.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class NairobiRoutingBaseException(Exception):
    """Root exception.  Every custom error inherits from this."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "An unexpected error occurred.",
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "detail": self.detail,
        }


# ── Graph / Spatial ──────────────────────────────────────────────────────────

class GraphNotLoadedError(NairobiRoutingBaseException):
    """Raised when spatial algorithms are called before the road graph is ready."""
    status_code = 503
    error_code = "GRAPH_NOT_LOADED"

    def __init__(self) -> None:
        super().__init__(
            "Nairobi road graph is not yet loaded. "
            "The server may still be initialising — please retry in a few seconds."
        )


class GraphDownloadError(NairobiRoutingBaseException):
    """Raised when OSMnx fails to download the road network."""
    status_code = 503
    error_code = "GRAPH_DOWNLOAD_FAILED"


class CoordinateSnapError(NairobiRoutingBaseException):
    """Raised when a GPS coordinate cannot be snapped to the road network."""
    status_code = 422
    error_code = "COORDINATE_SNAP_FAILED"


# ── Routing ──────────────────────────────────────────────────────────────────

class RoutingError(NairobiRoutingBaseException):
    """Generic routing failure."""
    status_code = 500
    error_code = "ROUTING_FAILED"


class OSRMConnectionError(NairobiRoutingBaseException):
    """OSRM API is unreachable."""
    status_code = 503
    error_code = "OSRM_UNAVAILABLE"

    def __init__(self, url: str) -> None:
        super().__init__(
            f"Could not reach OSRM at {url}. "
            "Street-network routing is unavailable — falling back to Haversine."
        )


class OSRMRouteNotFound(NairobiRoutingBaseException):
    """OSRM returned no route between two points."""
    status_code = 422
    error_code = "OSRM_NO_ROUTE"


class UnsupportedRoutingMethod(NairobiRoutingBaseException):
    """Client requested a routing method that doesn't exist."""
    status_code = 400
    error_code = "UNSUPPORTED_ROUTING_METHOD"

    def __init__(self, method: str) -> None:
        super().__init__(
            f"'{method}' is not a supported routing method. "
            "Valid options: euclidean, haversine, street_network"
        )


# ── Simulation ───────────────────────────────────────────────────────────────

class SimulationNotFoundError(NairobiRoutingBaseException):
    """Client referenced a simulation session that doesn't exist."""
    status_code = 404
    error_code = "SIMULATION_NOT_FOUND"

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Simulation session '{session_id}' not found.")


class SimulationLimitExceededError(NairobiRoutingBaseException):
    """Requested order/driver count exceeds configured limits."""
    status_code = 400
    error_code = "SIMULATION_LIMIT_EXCEEDED"


# ── Clustering ───────────────────────────────────────────────────────────────

class ClusteringError(NairobiRoutingBaseException):
    """Raised when clustering fails to produce any valid clusters."""
    status_code = 500
    error_code = "CLUSTERING_FAILED"


# ── Redis ────────────────────────────────────────────────────────────────────

class RedisConnectionError(NairobiRoutingBaseException):
    """Redis is unreachable — simulation state cannot be persisted."""
    status_code = 503
    error_code = "REDIS_UNAVAILABLE"