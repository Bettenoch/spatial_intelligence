"""
app/api/routes/algorithms.py
─────────────────────────────────────────────────────────────────────────────
REST endpoints serving algorithm educational content.

GET /algorithms            → List all algorithms with summaries
GET /algorithms/{id}       → Full explanation for one algorithm
GET /concepts/{id}         → Conceptual explanation (clustering, VRP, etc.)
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.education_service import (
    get_all_algorithms,
    get_algorithm,
    get_concept,
)

router = APIRouter(prefix="/api", tags=["education"])


@router.get("/algorithms")
async def list_algorithms():
    """Return all algorithm summaries for the sidebar menu."""
    algorithms = get_all_algorithms()
    # Return lightweight summary (no full explanation text)
    return [
        {
            "id": a["id"],
            "name": a["name"],
            "category": a.get("category"),
            "short_description": a.get("short_description"),
            "complexity": a.get("complexity"),
        }
        for a in algorithms
    ]


@router.get("/algorithms/{algorithm_id}")
async def get_algorithm_detail(algorithm_id: str):
    """Return the full educational content for one algorithm."""
    algo = get_algorithm(algorithm_id)
    if not algo:
        raise HTTPException(
            status_code=404,
            detail=f"Algorithm '{algorithm_id}' not found.",
        )
    return algo


@router.get("/concepts/{concept_id}")
async def get_concept_detail(concept_id: str):
    """Return a high-level concept explanation."""
    concept = get_concept(concept_id)
    if not concept:
        raise HTTPException(
            status_code=404,
            detail=f"Concept '{concept_id}' not found.",
        )
    return concept