"""
app/algorithms/routing/osrm_client.py
─────────────────────────────────────────────────────────────────────────────
Async HTTP client wrapping the OSRM public routing API.

OSRM (Open Source Routing Machine) routes along real OpenStreetMap roads.
The public demo server (router.project-osrm.org) is free, no key required.

Endpoints used:
  /route/v1/driving/{coords}   → single route with geometry
  /table/v1/driving/{coords}   → distance/time matrix for multiple points

Rate limiting:
  The public OSRM demo server has no formal rate limit but is a shared
  resource.  We keep requests minimal — one per cluster per simulation.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger

from app.core.config import settings
from app.core.exceptions import OSRMConnectionError, OSRMRouteNotFound


class OSRMClient:
    """
    Thin async wrapper around the OSRM HTTP API.
    Instantiate once and reuse (keeps connection pool alive).
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.osrm_base_url).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Route endpoint ────────────────────────────────────────────────────────

    async def get_route(
        self,
        waypoints: List[Tuple[float, float]],  # [(lat, lon), …]
        overview: str = "full",
        geometries: str = "geojson",
    ) -> Dict[str, Any]:
        """
        Get a route through ordered waypoints.

        Args:
            waypoints:   List of (lat, lon) in visit order
            overview:    "full" | "simplified" | "false"
            geometries:  "geojson" | "polyline"

        Returns:
            Raw OSRM route response dict.

        Raises:
            OSRMConnectionError: Cannot reach OSRM server.
            OSRMRouteNotFound:   OSRM returned no valid route.
        """
        # OSRM takes coordinates as lon,lat (note the order)
        coord_str = ";".join(f"{lon},{lat}" for lat, lon in waypoints)
        url = (
            f"{self.base_url}/route/v1/driving/{coord_str}"
            f"?overview={overview}&geometries={geometries}&steps=false"
        )

        try:
            client = await self._get_client()
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        except httpx.ConnectError as exc:
            raise OSRMConnectionError(self.base_url) from exc
        except httpx.TimeoutException as exc:
            raise OSRMConnectionError(f"{self.base_url} (timeout)") from exc
        except Exception as exc:
            logger.warning(f"OSRM request failed: {exc}")
            raise OSRMConnectionError(self.base_url) from exc

        if data.get("code") != "Ok" or not data.get("routes"):
            raise OSRMRouteNotFound(
                f"OSRM returned no route for {len(waypoints)} waypoints"
            )

        return data

    async def get_route_geometry_and_distance(
        self,
        waypoints: List[Tuple[float, float]],
    ) -> Tuple[Dict[str, Any], float, float]:
        """
        Convenience method: returns (geojson_feature, distance_km, duration_minutes).

        Falls back gracefully if OSRM is unavailable.
        """
        try:
            data = await self.get_route(waypoints)
            route = data["routes"][0]
            distance_km = route["distance"] / 1000.0
            duration_min = route["duration"] / 60.0
            geometry = route["geometry"]  # GeoJSON LineString

            geojson = {
                "type": "Feature",
                "geometry": geometry,
                "properties": {"method": "street_network", "source": "osrm"},
            }
            return geojson, round(distance_km, 3), round(duration_min, 1)

        except (OSRMConnectionError, OSRMRouteNotFound) as exc:
            logger.warning(f"  OSRM unavailable, falling back to Haversine: {exc}")
            # Fallback: haversine straight-line
            from app.algorithms.distance.haversine import (
                haversine_distance,
                build_haversine_geojson,
                nearest_neighbour_tour_haversine,
            )
            import numpy as np
            coords = np.array(waypoints)
            tour, total_dist = nearest_neighbour_tour_haversine(coords)
            geojson = build_haversine_geojson(coords, tour)
            geojson["properties"]["method"] = "haversine_fallback"
            duration_min = (total_dist / 30) * 60  # assume 30 km/h avg
            return geojson, round(total_dist, 3), round(duration_min, 1)

    # ── Table endpoint (distance matrix) ──────────────────────────────────────

    async def get_distance_table(
        self,
        waypoints: List[Tuple[float, float]],
    ) -> Dict[str, Any]:
        """
        Get a distance/duration matrix between all pairs of waypoints.

        Returns:
            Raw OSRM table response with 'durations' and 'distances' matrices.
        """
        coord_str = ";".join(f"{lon},{lat}" for lat, lon in waypoints)
        url = f"{self.base_url}/table/v1/driving/{coord_str}?annotations=distance,duration"

        try:
            client = await self._get_client()
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning(f"OSRM table request failed: {exc}")
            raise OSRMConnectionError(self.base_url) from exc


# ── Module-level singleton ─────────────────────────────────────────────────────

osrm_client = OSRMClient()