"""
models/cluster.py
─────────────────────────────────────────────────────────────────────────────
Cluster data model — a group of nearby orders assigned to one driver run.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

# Pre-defined colour palette — one per cluster, cycling
CLUSTER_COLORS = [
    "#FF6B35",  # orange
    "#4ECDC4",  # teal
    "#45B7D1",  # sky blue
    "#96CEB4",  # sage
    "#FFEAA7",  # yellow
    "#DDA0DD",  # plum
    "#98D8C8",  # mint
    "#F7DC6F",  # gold
    "#BB8FCE",  # lavender
    "#85C1E9",  # light blue
]


class Cluster(BaseModel):
    id: str = Field(default_factory=lambda: f"cls_{uuid4().hex[:6]}")
    order_ids: List[str] = Field(default_factory=list)
    centroid_lat: float
    centroid_lon: float
    color: str = "#FF6B35"
    driver_id: Optional[str] = None
    zone_label: str = ""   # e.g. "Westlands cluster"
    algorithm_used: str = "dbscan"

    @property
    def size(self) -> int:
        return len(self.order_ids)