<div align="center">

# 🧠 GeoIntelligence — Spatial Intelligence Backend

**FastAPI backend powering the Smart Nairobi Delivery Routing simulation platform**

*Real road networks · DBSCAN clustering · OSRM routing · WebSocket event streaming*

[![Frontend](https://img.shields.io/badge/Frontend-Live%20Demo-00E5CC?style=for-the-badge&logo=vercel&logoColor=white)](https://nairobi-routing-frontend.vercel.app/)
[![API Docs](https://img.shields.io/badge/API%20Docs-Swagger%20UI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://your-backend-domain.com/docs)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat-square&logo=redis&logoColor=white)
![OSMnx](https://img.shields.io/badge/OSMnx-OpenStreetMap-7EBC6F?style=flat-square)

</div>

---

## What This Is

The spatial intelligence engine behind the [Smart Nairobi Delivery Routing](https://nairobi-routing-frontend.vercel.app/) platform.

This backend handles everything the map needs: generating realistic delivery scenarios across Nairobi, running spatial clustering and route optimisation algorithms, and streaming every event to the frontend over WebSocket in real time.

The system downloads and caches the actual Nairobi road network from OpenStreetMap — 36,000+ nodes and 9,000+ edges — and uses it for genuine street-level routing.

---

## Screenshots

**Live simulation — DBSCAN clusters formed, routes computed, drivers en route**

![Simulation Overview](https://raw.githubusercontent.com/Bettenoch/nairobi_routing_frontend/main/public/screenshots/simulation-overview.png)

**DBSCAN clustering — orders grouped by geographic density**

![Order Clustering](https://raw.githubusercontent.com/Bettenoch/nairobi_routing_frontend/main/public/screenshots/order-clustering.png)

**Route animation — real Nairobi streets via OSRM**

![Route Animation](https://raw.githubusercontent.com/Bettenoch/nairobi_routing_frontend/main/public/screenshots/route-animation.png)

**Completion summary — savings calculated vs naive per-order routing**

![Completion Overlay](https://raw.githubusercontent.com/Bettenoch/nairobi_routing_frontend/main/public/screenshots/completion-overlay.png)

---

## Architecture

```
Client (React Frontend — Vercel)
            │
    REST + WebSocket
            │
            ▼
FastAPI Backend (Docker — VPS)
            │
            ▼
Service Layer
├── simulation_service.py   — orchestrates the full simulation run
├── routing_service.py      — dispatches to correct routing algorithm
└── metrics_service.py      — calculates savings vs naive baseline
            │
            ▼
Algorithm Layer (pure — no API or service logic)
├── clustering/
│   ├── dbscan.py           — DBSCAN with UTM Zone 37S projection
│   ├── kmeans.py           — K-Means for fixed driver count
│   └── hdbscan.py          — Hierarchical DBSCAN fallback
├── routing/
│   ├── osrm_client.py      — async OSRM HTTP client
│   ├── dijkstra.py         — NetworkX shortest path wrapper
│   ├── astar.py            — A* with Haversine heuristic
│   └── vrp_solver.py       — OR-Tools VRP solver
└── distance/
    ├── euclidean.py        — straight-line baseline
    ├── haversine.py        — great-circle distance
    └── street_network.py   — road graph distance matrix
            │
            ▼
Spatial Graph Engine
OSMnx → Nairobi road graph → cached as pickle
NetworkX → graph traversal and shortest path
OSRM → real street routing via public API
```

---

## Algorithms Implemented

### Clustering

| Algorithm | Module | When Used |
|---|---|---|
| **DBSCAN** | `algorithms/clustering/dbscan.py` | Default — discovers clusters from data, handles noise |
| **K-Means** | `algorithms/clustering/kmeans.py` | When driver count is known and density is uniform |
| **HDBSCAN** | `algorithms/clustering/hdbscan.py` | Varying density across city zones (Rongai vs CBD) |

All clustering algorithms project coordinates to **UTM Zone 37S (EPSG:32737)** before distance computation — the correct metre-based system for Nairobi. Running DBSCAN on raw WGS84 lat/lon produces incorrect clusters near the equator.

### Routing

| Algorithm | Module | When Used |
|---|---|---|
| **OSRM** | `algorithms/routing/osrm_client.py` | `street_network` mode — real Nairobi roads |
| **Dijkstra** | `algorithms/routing/dijkstra.py` | Graph shortest path, OSRM fallback |
| **A\*** | `algorithms/routing/astar.py` | Single-pair queries — 4–10× faster than Dijkstra |
| **VRP** | `algorithms/routing/vrp_solver.py` | Multi-driver joint optimisation via OR-Tools |

### Distance

| Method | Module | What It Measures |
|---|---|---|
| **Euclidean** | `algorithms/distance/euclidean.py` | Straight-line, ignores Earth's curvature |
| **Haversine** | `algorithms/distance/haversine.py` | Great-circle distance — accurate but ignores roads |
| **Street network** | `algorithms/distance/street_network.py` | Actual road distance from the graph |

---

## Simulation Flow

```
POST /api/simulate
      │
      ▼
build_scenario()
├── generate_restaurants()   — anchored to real commercial zones
├── generate_orders()        — weighted by neighbourhood hotspot density
│                              each order snapped to nearest road node
└── generate_drivers()       — spread across depot zones (CBD, Westlands, Karen…)
      │
      ▼
run_simulation()  (background task — streams events over WebSocket)
      │
      ├── Phase 1: Emit RESTAURANT_CREATED events
      ├── Phase 2: Emit ORDER_CREATED events (one per order, animated)
      ├── Phase 3: DBSCAN clustering → CLUSTER_FORMED events
      ├── Phase 4: Route computation → ROUTE_COMPUTED + DRIVER_ASSIGNED events
      ├── Phase 5: Driver animation → DRIVER_MOVED + DELIVERY_COMPLETED events
      └── Phase 6: SIMULATION_COMPLETED + final METRICS_UPDATED
```

---

## WebSocket Events Reference

All events follow the schema: `{ event: string, session_id: string, timestamp: datetime, data: {} }`

| Event | Trigger | Key Data |
|---|---|---|
| `RESTAURANT_CREATED` | Phase 1 | `lat`, `lon`, `name`, `zone`, `cuisine_type` |
| `ORDER_CREATED` | Phase 2 | `lat`, `lon`, `zone`, `order_type`, `restaurant_lat/lon` |
| `CLUSTER_FORMED` | Phase 3 | `order_ids`, `centroid_lat/lon`, `color`, `zone_label` |
| `DRIVER_ASSIGNED` | Phase 4 | `driver_id`, `driver_name`, `cluster_id`, `order_count` |
| `ROUTE_COMPUTED` | Phase 4 | `geojson`, `total_distance_km`, `naive_distance_km`, `color` |
| `DRIVER_MOVED` | Phase 5 | `lat`, `lon`, `progress_pct`, `phase` (pickup/delivery) |
| `DELIVERY_COMPLETED` | Phase 5 | `order_id`, `driver_name`, `time_taken_minutes`, `distance_km` |
| `METRICS_UPDATED` | Phases 4–5 | Full metrics snapshot — distances, fuel, cost, CO₂ |
| `DELIVERY_TABLE` | Phase 6 | Complete delivery records array for the results table |
| `SIMULATION_COMPLETED` | Phase 6 | `total_deliveries`, `total_savings_pct`, `duration_seconds` |

---

## API Endpoints

```
GET  /                          → Health check + graph stats
GET  /api/health                → Graph ready state + active simulation count
POST /api/simulate              → Start a new simulation
GET  /api/scenario              → Default simulation config
GET  /api/simulation/{id}       → Simulation state + delivery records
GET  /api/algorithms            → List all algorithm summaries
GET  /api/algorithms/{id}       → Full algorithm explanation + formula
GET  /api/concepts/{id}         → Concept explanation (clustering, VRP, etc.)
GET  /api/metrics/{id}          → Final metrics for a completed simulation
WS   /ws/simulation/{id}        → Live event stream for a simulation session
```

Full interactive docs at `/docs` (Swagger UI) and `/redoc` when the server is running.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI + Uvicorn (uvloop) |
| Real-time | WebSockets — native FastAPI support |
| Road network | OSMnx 1.9 → downloads from OpenStreetMap |
| Graph algorithms | NetworkX 3.3 |
| Spatial operations | GeoPandas, Shapely, PyProj |
| Clustering | scikit-learn (DBSCAN, KMeans) + hdbscan |
| Street routing | OSRM public API (async via httpx) |
| VRP solver | Google OR-Tools 9.10 |
| Caching | Redis 7.2 (Alpine) |
| Logging | Loguru |
| Containerisation | Docker + Docker Compose |
| Reverse proxy | Nginx (WebSocket upgrade headers included) |

---

## Project Structure

```
spatial_intelligence/
│
├── app/
│   ├── main.py                        # FastAPI app, lifespan, CORS, routers
│   │
│   ├── core/
│   │   ├── config.py                  # Pydantic settings from environment
│   │   ├── graph_loader.py            # OSMnx graph download + cache singleton
│   │   └── exceptions.py             # Custom exception hierarchy
│   │
│   ├── algorithms/
│   │   ├── clustering/
│   │   │   ├── dbscan.py              # UTM-projected DBSCAN
│   │   │   ├── kmeans.py              # K-Means spatial clustering
│   │   │   └── hdbscan.py            # HDBSCAN with DBSCAN fallback
│   │   ├── routing/
│   │   │   ├── osrm_client.py         # Async OSRM HTTP client + fallback
│   │   │   ├── dijkstra.py            # NetworkX Dijkstra wrapper
│   │   │   ├── astar.py               # A* with Haversine heuristic
│   │   │   └── vrp_solver.py          # OR-Tools VRP + greedy fallback
│   │   └── distance/
│   │       ├── euclidean.py           # Straight-line nearest-neighbour TSP
│   │       ├── haversine.py           # Great-circle distance + TSP
│   │       └── street_network.py      # Road graph distance matrix
│   │
│   ├── services/
│   │   ├── simulation_service.py      # Full simulation orchestration + timing logs
│   │   ├── routing_service.py         # Strategy pattern — dispatches to algorithm
│   │   └── metrics_service.py         # Savings vs naive baseline calculation
│   │
│   ├── simulation/
│   │   ├── scenario_builder.py        # Assembles SimulationState from config
│   │   ├── order_generator.py         # Weighted hotspot sampling + road snapping
│   │   ├── driver_generator.py        # Depot-anchored driver placement
│   │   └── restaurant_generator.py    # Commercial zone restaurant placement
│   │
│   ├── websocket/
│   │   ├── manager.py                 # Connection registry + broadcast
│   │   └── events.py                  # All Pydantic event models
│   │
│   ├── api/
│   │   ├── routes/
│   │   │   ├── simulation.py          # /api/simulate, /api/simulation/{id}
│   │   │   ├── algorithms.py          # /api/algorithms, /api/concepts
│   │   │   └── metrics.py             # /api/metrics/{id}
│   │   └── websocket_routes.py        # WS /ws/simulation/{session_id}
│   │
│   ├── models/
│   │   ├── order.py                   # Order schema with restaurant fields
│   │   ├── driver.py                  # Driver with status + capacity
│   │   ├── cluster.py                 # Cluster with colour palette
│   │   ├── route.py                   # Route with GeoJSON geometry
│   │   ├── restaurant.py              # Restaurant with road node snap
│   │   └── simulation.py              # Full simulation state + config
│   │
│   └── data/
│       ├── nairobi_zones.geojson       # Neighbourhood polygons
│       ├── hotspots.json               # Order hotspot coordinates + weights
│       └── algorithm_content.json      # Educational content for learning drawer
│
├── scripts/
│   └── preload_graph.py               # One-time OSM graph download + cache
│
├── tests/
│   ├── test_algorithms.py
│   ├── test_simulation.py
│   └── test_websocket.py
│
├── nginx/
│   └── conf.d/nairobi.conf            # Nginx reverse proxy + WebSocket upgrade
│
├── docker-compose.yml                 # api + redis + preloader services
├── Dockerfile                         # Single-stage Python 3.11 + GDAL build
├── requirements.txt
├── .env.example
└── README.md
```

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Docker + Docker Compose (recommended)
- Or: libgdal, libgeos, libproj installed locally for native setup

### Option A — Docker (recommended)

```bash
git clone https://github.com/Bettenoch/spatial_intelligence.git
cd spatial_intelligence

cp .env.example .env
# Edit .env — set CORS_ORIGINS to your frontend URL
```

**First run — preload the road graph (do this once):**

```bash
docker compose run --rm preloader
# Downloads Nairobi road network from OpenStreetMap (~4–12 minutes first time)
# Saved to the graph_cache Docker volume — subsequent starts take ~3 seconds
```

**Start the API:**

```bash
docker compose up -d api redis
docker compose logs -f api
```

The API is available at `http://localhost:8080`.

### Option B — Local Python

```bash
git clone https://github.com/Bettenoch/spatial_intelligence.git
cd spatial_intelligence

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Preload the graph
python scripts/preload_graph.py

# Start the API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Environment Variables

```env
# OSRM routing (default uses public demo server — no key needed)
OSRM_BASE_URL=http://router.project-osrm.org

# Redis
REDIS_URL=redis://localhost:6379

# Graph cache path
NAIROBI_GRAPH_CACHE_PATH=./cache/nairobi_graph.pkl

# Simulation limits
SIMULATION_MAX_ORDERS=60
SIMULATION_MAX_DRIVERS=8

# CORS (comma-separated, include your frontend URL)
CORS_ORIGINS=http://localhost:3000,https://nairobi-routing-frontend.vercel.app

# Logging
LOG_LEVEL=INFO
APP_ENV=development
```

---

## Production Deployment (VPS)

### 1. Clone and configure

```bash
git clone https://github.com/Bettenoch/spatial_intelligence.git
cd spatial_intelligence
cp .env.example .env
# Set APP_ENV=production, LOG_LEVEL=WARNING, CORS_ORIGINS=your frontend domain
```

### 2. Preload the graph

```bash
docker compose run --rm preloader
```

### 3. Start services

```bash
docker compose up -d api redis
```

### 4. Nginx reverse proxy

The `nginx/conf.d/nairobi.conf` file includes the correct WebSocket upgrade headers. Replace `YOUR_DOMAIN.com` with your actual domain, add SSL with Certbot, and reload Nginx.

Critical WebSocket config (already in the file):

```nginx
location /ws/ {
    proxy_pass         http://api_backend;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade    $http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_read_timeout 3600s;
}
```

### 5. Check health

```bash
curl https://your-domain.com/api/health
# → {"status":"ok","graph":{"ready":true,"node_count":36896,...}}
```

### Monitoring

```bash
# Live logs with timing diagnostics
docker compose logs -f --tail=100 api | grep "⏱"

# Container resource usage
docker stats --no-stream

# Graph cache size
docker exec nairobi_api ls -lh /app/cache/
```

---

## The Road Graph

On first startup (or when `preload_graph.py` runs), the backend downloads the Nairobi drivable road network from OpenStreetMap via OSMnx:

- **~36,896 nodes** (road intersections and endpoints)
- **~8,984 edges** (road segments with length and speed limit attributes)
- **Bounding box:** N -1.163, S -1.444, E 37.010, W 36.650
- **Cached** as a pickle file (~250 MB) — subsequent starts load in ~3 seconds

The graph is enriched with `edge_speeds` and `edge_travel_times` using OSM speed limit data, enabling realistic duration estimates alongside road distances.

---

## Metrics Calculation

The savings metric compares two scenarios for the same set of orders:

**Naive baseline:** Every order gets a separate round trip from its driver's starting position. Total naive distance = `Σ (driver → order → driver) × 2` for each order independently.

**Optimised:** Orders are clustered and batched. One driver handles multiple stops in a single run. Total optimised distance = sum of all computed route lengths.

For `street_network` mode, the naive baseline is scaled by Nairobi's **circuity factor of 1.4×** to ensure an apples-to-apples comparison (road km vs road km, not road km vs straight-line km).

```
savings_pct = (naive_km - optimised_km) / naive_km × 100
fuel_saved_L = distance_saved_km / 100 × 10.0   (motorbike: 10L/100km)
cost_saved_KES = fuel_saved_L × 210.0             (KES/litre, 2024 avg)
co2_saved_kg = fuel_saved_L × 2.31               (kg CO₂ per litre petrol)
```

---

## Key Engineering Notes

**WebSocket race condition fix.** The backend waits up to 10 seconds for a WebSocket client to connect before starting event emission. This prevents the common failure mode where the simulation fires all early events (restaurants, orders, clustering) before the frontend WebSocket is open, causing the map to appear stuck until the routing phase.

**Coordinate validation.** Order coordinates are validated for `(0, 0)` and non-finite values at both generation time and before any event emission. The `isValidCoord` guard in the frontend provides a second layer of defence.

**Nearest-node snapping.** Every order and driver position is snapped to the nearest road network node using `ox.nearest_nodes()`. This ensures routing stays on the actual graph rather than interpolating from arbitrary GPS coordinates.

---

## Author

**Bett Enoch**
GIS Developer · Nairobi, Kenya

[![Portfolio](https://img.shields.io/badge/Portfolio-bett--xp.vercel.app-00E5CC?style=flat-square)](https://bett-xp.vercel.app/)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-bettenoch-0A66C2?style=flat-square&logo=linkedin)](https://www.linkedin.com/in/bettenoch/)
[![GitHub](https://img.shields.io/badge/GitHub-Bettenoch-181717?style=flat-square&logo=github)](https://github.com/Bettenoch)

---

## Related Repository

The React + TypeScript frontend lives here:
**[nairobi_routing_frontend](https://github.com/Bettenoch/nairobi_routing_frontend)**

Live demo: **[nairobi-routing-frontend.vercel.app](https://nairobi-routing-frontend.vercel.app/)**

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
  <sub>Built with real OpenStreetMap data · Nairobi road network © OpenStreetMap contributors</sub>
</div>