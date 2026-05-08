"""
scripts/preload_graph.py
─────────────────────────────────────────────────────────────────────────────
One-time script: downloads the Nairobi road network from OpenStreetMap and
caches it to disk as a pickle file.

Run this ONCE before deploying to avoid the 30-second cold-start download
on the production server.  After this script completes, subsequent server
starts load the graph in ~3 seconds from cache.

Usage:
    python scripts/preload_graph.py

    # Or from project root:
    uv run python scripts/preload_graph.py

Output:
    ./cache/nairobi_graph.pkl  (~25–40 MB)

The script can also be used to force-refresh a stale cache:
    python scripts/preload_graph.py --force
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

# Ensure the project root is on sys.path so `from app.core...` works

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def main(force: bool = False) -> None:
    from loguru import logger
    from app.core.config import settings

    cache_path = Path(settings.nairobi_graph_cache_path)

    if cache_path.exists() and not force:
        import pickle
        size_mb = cache_path.stat().st_size / (1024 * 1024)
        logger.info(f"✅ Cache already exists at {cache_path} ({size_mb:.1f} MB)")
        logger.info("   Use --force to re-download.")
        return

    logger.info("⬇️  Downloading Nairobi road network from OpenStreetMap…")
    logger.info(
        f"   Bounding box: N={settings.nairobi_bbox_north}, "
        f"S={settings.nairobi_bbox_south}, "
        f"E={settings.nairobi_bbox_east}, "
        f"W={settings.nairobi_bbox_west}"
    )
    logger.info("   This may take 20–60 seconds depending on your connection.")

    start = time.perf_counter()

    try:
        import osmnx as ox
        import networkx as nx

        # Configure OSMnx caching
        try:
            ox.settings.use_cache = True  # pyright: ignore[reportAttributeAccessIssue]
            ox.settings.cache_folder = "./cache/osmnx_http_cache"  # pyright: ignore[reportAttributeAccessIssue]
        except AttributeError:
            pass

        # Detect API version
        import importlib.metadata as _meta
        try:
            ox_ver = tuple(int(x) for x in _meta.version("osmnx").split(".")[:2])
        except Exception:
            ox_ver = (1, 9)

        logger.info(f"   osmnx version: {ox_ver[0]}.{ox_ver[1]}")

        if ox_ver >= (1, 9):
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
            G_raw = ox.graph_from_bbox(
                north=settings.nairobi_bbox_north,
                south=settings.nairobi_bbox_south,
                east=settings.nairobi_bbox_east,
                west=settings.nairobi_bbox_west,
                network_type="drive",
                simplify=True,
                retain_all=False,
            )

        # Ensure MultiDiGraph
        if isinstance(G_raw, nx.MultiDiGraph):
            G = G_raw
        else:
            G = nx.MultiDiGraph(G_raw)

        logger.info(f"   Downloaded: {len(G.nodes):,} nodes, {len(G.edges):,} edges")

        # Enrich with speed and travel time
        logger.info("   Adding edge speeds and travel times…")
        G = ox.add_edge_speeds(G)
        G = ox.add_edge_travel_times(G)

        # Save to cache
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "wb") as f:
            pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

        elapsed = time.perf_counter() - start
        size_mb = cache_path.stat().st_size / (1024 * 1024)
        logger.info(
            f"✅ Graph cached to {cache_path} "
            f"({size_mb:.1f} MB, {elapsed:.1f}s)"
        )
        logger.info("   The backend will now start in ~3 seconds instead of ~30.")

    except Exception as exc:
        logger.error(f"❌ Failed to download graph: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pre-download and cache the Nairobi OSMnx road graph."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if cache already exists",
    )
    args = parser.parse_args()
    main(force=args.force)