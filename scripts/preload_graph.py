"""
scripts/preload_graph.py
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

# /app/scripts/preload_graph.py  →  parent = /app/scripts  →  parent.parent = /app
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(force: bool = False) -> None:
    from loguru import logger
    from app.core.config import settings

    cache_path = Path(settings.nairobi_graph_cache_path)

    if cache_path.exists() and not force:
        size_mb = cache_path.stat().st_size / (1024 * 1024)
        logger.info(f"✅ Cache already exists at {cache_path} ({size_mb:.1f} MB)")
        logger.info("   Use --force to re-download.")
        return

    logger.info("⬇️  Downloading Nairobi road network using graph_from_place...")

    start = time.perf_counter()

    try:
        import osmnx as ox
        import networkx as nx

        # OSMnx caching
        try:
            ox.settings.use_cache = True
            ox.settings.cache_folder = "./cache/osmnx_http_cache"
            ox.settings.log_console = True
        except AttributeError:
            pass

        logger.info("   Fetching Nairobi boundary and road network... (this may take 4–12 minutes)")

        G_raw = ox.graph_from_place(
            "Nairobi, Kenya",
            network_type="drive",
            simplify=True,
            retain_all=False,
            truncate_by_edge=True,
        )

        if isinstance(G_raw, nx.MultiDiGraph):
            G: nx.MultiDiGraph = G_raw
        else:
            G = nx.MultiDiGraph(G_raw)

        logger.info(f"   Downloaded: {len(G.nodes):,} nodes, {len(G.edges):,} edges")

        # Enrich graph
        logger.info("   Adding speeds and travel times...")
        G = ox.add_edge_speeds(G)
        G = ox.add_edge_travel_times(G)

        # Save cache
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "wb") as f:
            pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

        elapsed = time.perf_counter() - start
        size_mb = cache_path.stat().st_size / (1024 * 1024)
        logger.success(
            f"✅ Graph successfully cached to {cache_path} "
            f"({size_mb:.1f} MB, {elapsed:.1f}s)"
        )

    except Exception as exc:
        logger.error(f"❌ Failed to download graph: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(force=args.force)