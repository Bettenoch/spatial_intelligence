"""
services/education_service.py
─────────────────────────────────────────────────────────────────────────────
Serves educational content for each algorithm and concept used in the
simulation.  Content is loaded from data/algorithm_content.json.

The learning drawer in the frontend calls GET /algorithms/{id} to fetch
the explanation for whatever the user just interacted with.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


_CONTENT_PATH = Path(__file__).parent.parent / "data" / "algorithm_content.json"
_cache: Optional[Dict[str, Any]] = None


def _load_content() -> Dict[str, Any]:
    global _cache
    if _cache is None:
        if _CONTENT_PATH.exists():
            with open(_CONTENT_PATH) as f:
                _cache = json.load(f)
        else:
            logger.warning(f"algorithm_content.json not found at {_CONTENT_PATH}")
            _cache = {"algorithms": [], "concepts": []}
    assert _cache is not None
    return _cache


def get_all_algorithms() -> List[Dict[str, Any]]:
    """Return the full list of algorithm explanations."""
    return _load_content().get("algorithms", [])


def get_algorithm(algorithm_id: str) -> Optional[Dict[str, Any]]:
    """Return a single algorithm explanation by its ID."""
    for algo in get_all_algorithms():
        if algo.get("id") == algorithm_id:
            return algo
    return None


def get_concept(concept_id: str) -> Optional[Dict[str, Any]]:
    """Return a concept explanation (e.g. 'clustering', 'vrp')."""
    for concept in _load_content().get("concepts", []):
        if concept.get("id") == concept_id:
            return concept
    return None