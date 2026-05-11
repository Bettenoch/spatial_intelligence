"""
app/main.py
─────────────────────────────────────────────────────────────────────────────
FastAPI application entry point.

Startup sequence:
  1. Load configuration
  2. Configure logging
  3. Initialise Nairobi road graph (async, runs in thread pool)
  4. Mount all routers
  5. Server ready

This module is the only place where all components are wired together.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.config import settings
from app.core.exceptions import NairobiRoutingBaseException
from app.core.graph_loader import graph_loader

# ── Configure loguru ─────────────────────────────────────────────────────────

logger.remove()
logger.add(
    sys.stdout,
    level=settings.log_level.upper(),
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    colorize=True,
)


# ── Application lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once on startup and once on shutdown.
    Used to load the road graph and clean up resources.
    """
    logger.info("🚀 Smart Nairobi Delivery Routing — Backend starting…")
    logger.info(f"   Environment : {settings.app_env}")
    logger.info(f"   Log level   : {settings.log_level}")
    logger.info(f"   OSRM URL    : {settings.osrm_base_url}")

    # Load the Nairobi road graph (may take 3–30 seconds on first run)
    await graph_loader.initialize()

    yield  # Application runs here

    # Shutdown cleanup
    from app.algorithms.routing.osrm_client import osrm_client
    await osrm_client.close()
    logger.info("👋 Server shutting down — cleanup complete")


# ── Application factory ────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Smart Nairobi Delivery Routing API",
        description=(
            "GIS portfolio project demonstrating real-time delivery route "
            "optimisation across Nairobi using spatial algorithms, "
            "DBSCAN clustering, and live WebSocket streaming."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────

    @app.exception_handler(NairobiRoutingBaseException)
    async def routing_exception_handler(request, exc: NairobiRoutingBaseException):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    from app.api.routes.simulation import router as simulation_router
    from app.api.routes.algorithms import router as algorithms_router
    from app.api.routes.metrics import router as metrics_router
    from app.api.websocket_routes import router as ws_router

    app.include_router(simulation_router)
    app.include_router(algorithms_router)
    app.include_router(metrics_router)
    app.include_router(ws_router)

    # ── Root endpoint ─────────────────────────────────────────────────────────

    @app.get("/", tags=["root"])
    async def root():
        return {
            "project": "Smart Nairobi Delivery Routing",
            "status": "running",
            "graph_ready": graph_loader.is_ready(),
            "graph_stats": graph_loader.stats(),
            "docs": "/docs",
        }

    return app


app = create_app()


# ── Dev server entrypoint ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )