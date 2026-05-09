# ─────────────────────────────────────────────────────────────────────────────
# Smart Nairobi Delivery Routing — Backend Dockerfile
#
# FIXED: Uses a single-stage build to avoid runtime shared-library name
# mismatches (libgdal32 vs libgdal35 etc. change with every Debian release).
# The image is ~100MB larger than a multi-stage build but is rock-solid.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────────────────────
# Install GDAL/GEOS/PROJ/SpatialIndex build + runtime libs in one layer.
# Using -dev packages ensures both headers AND .so runtime files are present.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    libspatialindex-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user ─────────────────────────────────────────────────────────────
RUN useradd -m -u 1000 appuser

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
RUN pip install --upgrade pip wheel --no-cache-dir

RUN pip install --no-cache-dir \
    "fastapi==0.111.0" \
    "uvicorn[standard]==0.30.1" \
    "websockets==12.0" \
    "python-multipart==0.0.9" \
    "osmnx==1.9.3" \
    "networkx==3.3" \
    "geopandas==0.14.4" \
    "shapely==2.0.4" \
    "pyproj==3.6.1" \
    "fiona==1.9.6" \
    "scikit-learn==1.5.0" \
    "scipy==1.13.0" \
    "numpy==1.26.4" \
    "pandas==2.2.2" \
    "httpx==0.27.0" \
    "ortools==9.10.4067" \
    "pydantic==2.7.1" \
    "pydantic-settings==2.3.1" \
    "python-dotenv==1.0.1" \
    "redis==5.0.4" \
    "hiredis==2.3.2" \
    "loguru==0.7.2" \
    "ujson==5.10.0" \
    "python-jose==3.3.0" \
    "anyio==4.4.0" \
    "hdbscan"

# ── Application source ────────────────────────────────────────────────────────
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser .env.example ./.env.example

# Cache directory for the OSMnx graph pickle (mounted as a Docker volume)
RUN mkdir -p /app/cache && chown appuser:appuser /app/cache

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--log-level", "info", \
     "--no-access-log"]