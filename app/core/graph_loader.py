"""
app/core/graph_loader.py
─────────────────────────────────────────────────────────────────────────────
Manages the Nairobi road network graph lifecycle:

  1. On first run  → downloads from OpenStreetMap via OSMnx (~30s)
  2. Caches to disk as a pickle file
  3. On subsequent runs → loads from cache (~3s)
  4. Exposes a singleton graph accessible app-wide

"""
from __future__ import annotations

import asyncio
import pickle
import time
from pathlib import Path
from typing import Optional, Tuple

import networkx as nx
from loguru import logger

from app.core.config import settings
from app.core.exceptions import GraphDownloadError, GraphNotLoadedError


class NairobiGraphLoader:
    """
    Singleton-style loader for the Nairobi OSMnx road graph.

    Usage:
        graph_loader = NairobiGraphLoader()
        await graph_loader.initialize()          # call once at startup
        G = graph_loader.get_graph()             # fast from anywhere
    """

    def __init__(self) -> None:
        self._graph: Optional[nx.MultiDiGraph] = None
        self._is_ready: bool = False
        self._load_time_seconds: float = 0.0
        self._node_count: int = 0
        self._edge_count: int = 0

    # ── Public API ────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """
        Async entry point called at FastAPI startup.
        Runs the blocking graph load in a thread pool so the event loop
        is never blocked during the 3–30 second load time.
        """
        logger.info("🗺️  Initialising Nairobi road graph…")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_graph_sync)
        logger.info(
            f"✅ Graph ready — {self._node_count:,} nodes, "
            f"{self._edge_count:,} edges — loaded in {self._load_time_seconds:.1f}s"
        )

    def get_graph(self) -> nx.MultiDiGraph:
        """Returns the loaded graph. Raises GraphNotLoadedError if not ready."""
        if not self._is_ready or self._graph is None:
            raise GraphNotLoadedError()
        return self._graph

    def is_ready(self) -> bool:
        return self._is_ready

    def stats(self) -> dict:
        return {
            "ready": self._is_ready,
            "node_count": self._node_count,
            "edge_count": self._edge_count,
            "load_time_seconds": self._load_time_seconds,
        }

    # ── Internal load logic ───────────────────────────────────────────────────

    def _load_graph_sync(self) -> None:
        """
        Synchronous graph load — runs in thread pool via initialize().
        Strategy: cache-first, download on miss.
        """
        start = time.perf_counter()
        cache_path = Path(settings.nairobi_graph_cache_path)

        if cache_path.exists():
            logger.info(f"📦 Loading graph from cache: {cache_path}")
            self._graph = self._load_from_cache(cache_path)
        else:
            logger.info("⬇️  Cache miss — downloading Nairobi road network from OSM…")
            logger.info("   This takes ~30 seconds on first run. Subsequent starts are fast.")
            self._graph = self._download_from_osm()
            self._save_to_cache(self._graph, cache_path)

        # Add travel times based on speed limits
        self._graph = self._enrich_graph(self._graph)

        self._node_count = len(self._graph.nodes)
        self._edge_count = len(self._graph.edges)
        self._load_time_seconds = time.perf_counter() - start
        self._is_ready = True

    def _download_from_osm(self) -> nx.MultiDiGraph:
        """
        Download the Nairobi drivable road network via OSMnx.

        Fix: OSMnx ≥1.0 exposes settings via ox.settings object attributes
        (not module-level). We set them directly on the settings object.
        Fix: cast return value explicitly to nx.MultiDiGraph.
        """
        try:
            import osmnx as ox

            # ── OSMnx settings (works for osmnx ≥1.0) ──────────────────────
            try:
                ox.settings.use_cache = True  # pyright: ignore[reportAttributeAccessIssue]
                ox.settings.cache_folder = "./cache/osmnx_http_cache"  # pyright: ignore[reportAttributeAccessIssue]
                ox.settings.log_console = False  # type: ignore[attr-defined]
            except AttributeError:
                pass  # Newer osmnx uses logging module — no action needed

            logger.info(
                f"  Bbox: N={settings.nairobi_bbox_north}, "
                f"S={settings.nairobi_bbox_south}, "
                f"E={settings.nairobi_bbox_east}, "
                f"W={settings.nairobi_bbox_west}"
            )

            # Detect osmnx version to handle bbox API change at 1.9
            import importlib.metadata as _meta
            try:
                _ox_version = tuple(
                    int(x) for x in _meta.version("osmnx").split(".")[:2]
                )
            except Exception:
                _ox_version = (1, 9)  # assume modern

            if _ox_version >= (1, 9):
                # New API: bbox=(left, bottom, right, top) = (west, south, east, north)
                G_raw = ox.graph_from_bbox(
                    bbox=(
                        settings.nairobi_bbox_west,
                        settings.nairobi_bbox_south,
                        settings.nairobi_bbox_east,
                        settings.nairobi_bbox_north,
                    ),
                    network_type="drive",
                    simplify=True,
                    retain_all=False,
                )
            else:
                # Legacy API: bbox=(north, south, east, west)
                G_raw = ox.graph_from_bbox(
                    north=settings.nairobi_bbox_north,
                    south=settings.nairobi_bbox_south,
                    east=settings.nairobi_bbox_east,
                    west=settings.nairobi_bbox_west,
                    network_type="drive",
                    simplify=True,
                    retain_all=False,
                )

            # Ensure we always return a MultiDiGraph
            if isinstance(G_raw, nx.MultiDiGraph):
                G: nx.MultiDiGraph = G_raw
            elif isinstance(G_raw, nx.DiGraph):
                G = nx.MultiDiGraph(G_raw)
            else:
                G = nx.MultiDiGraph(G_raw)

            logger.info(
                f"  Downloaded: {len(G.nodes):,} nodes, {len(G.edges):,} edges"
            )
            return G

        except Exception as exc:
            raise GraphDownloadError(
                f"OSMnx download failed: {exc}",
                detail={"original_error": str(exc)},
            ) from exc

    def _load_from_cache(self, path: Path) -> nx.MultiDiGraph:
        """Deserialise the graph from a pickle file."""
        try:
            with open(path, "rb") as f:
                G = pickle.load(f)
            logger.info(f"  Loaded: {len(G.nodes):,} nodes, {len(G.edges):,} edges")
            return G
        except Exception as exc:
            logger.warning(f"  Cache read failed ({exc}) — re-downloading from OSM…")
            return self._download_from_osm()

    def _save_to_cache(self, G: nx.MultiDiGraph, path: Path) -> None:
        """Serialise the graph to disk for fast subsequent loads."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)
            size_mb = path.stat().st_size / (1024 * 1024)
            logger.info(f"  Cached to {path} ({size_mb:.1f} MB)")
        except Exception as exc:
            logger.warning(f"  Could not write cache ({exc}) — continuing without cache")

    def _enrich_graph(self, G: nx.MultiDiGraph) -> nx.MultiDiGraph:
        """
        Add derived attributes to graph edges:
          - speed_kph: from OSM maxspeed or imputed by road type
          - travel_time: edge length / speed (seconds)
        """
        try:
            import osmnx as ox
            G = ox.add_edge_speeds(G)
            G = ox.add_edge_travel_times(G)
            return G
        except Exception as exc:
            logger.warning(f"  Graph enrichment skipped: {exc}")
            return G

    def nearest_node(self, lat: float, lon: float) -> Tuple[int, float]:
        """
        Snap a GPS coordinate to the nearest road network node.

        Fix: ox.nearest_nodes can return a scalar or 1-element array depending
        on whether scalars or arrays are passed as X/Y.  We use isinstance
        checks (not hasattr) so Pylance can narrow the type and int() receives
        a guaranteed scalar — resolving the reportArgumentType error.

        Returns:
            (node_id, distance_in_meters)
        """
        if not self._is_ready or self._graph is None:
            raise GraphNotLoadedError()
        try:
            import numpy as np
            import osmnx as ox

            result = ox.nearest_nodes(self._graph, X=lon, Y=lat, return_dist=True)
            node_id_raw, dist_raw = result

            # Use isinstance to narrow — Pylance understands isinstance, not hasattr
            if isinstance(node_id_raw, (list, np.ndarray)):
                # Array path: extract first element as a plain Python scalar
                node_id = int(node_id_raw[0])
                dist = float(dist_raw[0])
            else:
                # Scalar path: node_id_raw is int / np.integer / similar
                node_id = int(node_id_raw)  # type: ignore[arg-type]
                dist = float(dist_raw)      # type: ignore[arg-type]

            return node_id, dist

        except Exception as exc:
            from app.core.exceptions import CoordinateSnapError
            raise CoordinateSnapError(
                f"Cannot snap ({lat}, {lon}) to road network: {exc}"
            ) from exc


# ── Module-level singleton ────────────────────────────────────────────────────

graph_loader = NairobiGraphLoader()