"""
app/core/config.py
─────────────────────────────────────────────────────────────────────────────
Application-wide configuration loaded from environment variables / .env file.
Uses pydantic-settings for typed, validated settings — no raw os.getenv().
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central settings object.  All values resolve from environment or .env file.
    Never instantiate directly — use get_settings() below.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── OSRM ────────────────────────────────────────────────────────────────
    osrm_base_url: str = "http://router.project-osrm.org"

    # ── Redis ───────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

    # ── Graph cache ─────────────────────────────────────────────────────────
    nairobi_graph_cache_path: Path = Path("./cache/nairobi_graph.pkl")

    # ── Simulation limits ────────────────────────────────────────────────────
    simulation_max_orders: int = 60
    simulation_max_drivers: int = 8

    # ── Logging ─────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── CORS ────────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"

    # ── Environment ─────────────────────────────────────────────────────────
    app_env: str = "development"

    # ── Nairobi bounding box (approx) ────────────────────────────────────────
    # Used by OSMnx to download the graph
    nairobi_bbox_north: float = -1.163
    nairobi_bbox_south: float = -1.444
    nairobi_bbox_east: float = 37.010
    nairobi_bbox_west: float = 36.650

    # ── Fuel / cost constants (Kenyan context) ───────────────────────────────
    fuel_litres_per_100km: float = 10.0          # avg motorbike consumption
    fuel_price_kes_per_litre: float = 210.0       # KES per litre (2024 avg)
    co2_kg_per_litre: float = 2.31               # kg CO₂ per litre petrol

    # ── Clustering defaults ──────────────────────────────────────────────────
    dbscan_epsilon_km: float = 1.5               # cluster radius
    dbscan_min_samples: int = 2                  # min orders per cluster
    max_orders_per_driver: int = 6               # capacity constraint

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, v: str) -> str:
        """Keep as comma-separated string; parsing happens in main.py."""
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        """Returns CORS origins as a Python list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns a cached Settings singleton.
    Call this everywhere — it's fast after the first load.
    """
    return Settings()


# Module-level alias so callers can do `from app.core.config import settings`
settings = get_settings()