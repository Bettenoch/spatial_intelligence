# GeoDispatch AI

### Spatial Intelligence & Last-Mile Delivery Optimization Platform

GeoDispatch AI is a real-time spatial analytics and logistics simulation platform designed to explore how GIS, graph theory, clustering algorithms, and route optimization can improve last-mile delivery operations in urban environments.

The project simulates delivery operations in Nairobi using realistic road networks, spatial clustering, and intelligent dispatching strategies to demonstrate how transport and logistics companies reduce operational costs through route optimization and delivery batching.

---

# Problem Statement

Many small and medium delivery businesses operate inefficiently because deliveries are dispatched immediately after an order is received, even when nearby requests could be grouped together.

This results in:

* Increased fuel consumption
* Redundant routing
* Poor vehicle utilization
* Higher operational costs
* Longer delivery times

GeoDispatch AI explores how spatial intelligence systems can optimize these workflows using:

* GIS analysis
* Real road-network routing
* Clustering algorithms
* Vehicle routing optimization
* Real-time simulation

---

# Core Concept

The platform simulates a logistics environment where:

1. Customer orders arrive dynamically across Nairobi
2. Orders are spatially clustered using algorithms like DBSCAN
3. Nearby deliveries are batched together
4. Optimal routes are generated using graph algorithms
5. Metrics are calculated to estimate:

   * Fuel savings
   * Reduced travel distance
   * Delivery efficiency
   * Vehicle utilization

---

# Key Features

## Spatial Intelligence

* Nairobi road-network analysis using OpenStreetMap
* Real-world street routing
* Geographic clustering
* Distance analysis (Euclidean, Haversine, Street Network)

## Routing & Optimization

* Dijkstra shortest path
* A* pathfinding
* Vehicle Routing Problem (VRP) simulation
* Multi-stop delivery optimization

## Real-Time Simulation

* Live order generation
* Driver movement simulation
* WebSocket event streaming
* Dynamic dispatching

## Analytics & Metrics

* Fuel consumption estimation
* Cost reduction analysis
* Delivery performance metrics
* Route efficiency scoring

## Educational GIS Architecture

The project intentionally separates:

* pure algorithms,
* orchestration services,
* simulation state,
* and API delivery layers.

This mirrors real-world geospatial engineering systems.

---

# System Architecture

```text
Client (Frontend Dashboard)
            │
            ▼
FastAPI Backend (API + WebSockets)
            │
            ▼
Service Layer (Simulation Orchestration)
            │
            ▼
Algorithm Layer
├── Clustering
├── Routing
├── Distance Analysis
└── Optimization
            │
            ▼
Spatial Graph Engine
(OpenStreetMap + OSMnx + NetworkX)
```

---

# Architectural Principles

## Algorithms Stay Pure

The `algorithms/` layer contains:

* mathematical logic,
* graph traversal,
* clustering,
* optimization,
* routing calculations.

It contains **NO API logic** and **NO business orchestration**.

### Responsibilities

* Calculate
* Optimize
* Cluster
* Route
* Analyze

---

## Services Handle Orchestration

The `services/` layer coordinates application workflows.

### Responsibilities

* Execute simulations
* Manage simulation state
* Coordinate routing pipelines
* Aggregate metrics
* Stream events to clients

This separation creates:

* testable algorithms,
* reusable logic,
* cleaner architecture,
* and production-grade maintainability.

---

# Technology Stack

## Backend

* FastAPI
* WebSockets
* Redis
* Pydantic
* Loguru

## GIS / Spatial

* OSMnx
* GeoPandas
* Shapely
* PyProj
* NetworkX

## Optimization

* Scikit-learn
* OR-Tools
* SciPy

## Routing

* OSRM
* OpenStreetMap

---

# Project Structure

```text
spatial_intelligence/
│
├── app/
│   ├── algorithms/      # Pure routing + clustering algorithms
│   ├── services/        # Workflow orchestration
│   ├── simulation/      # Fake delivery environment
│   ├── websocket/       # Real-time streaming
│   ├── api/             # FastAPI routes
│   ├── models/          # Pydantic schemas
│   └── core/            # Config + graph loading
│
├── tests/
├── scripts/
└── data/
```

---

# Example Simulation Workflow

```text
Incoming Orders
      ↓
Spatial Clustering
      ↓
Route Optimization
      ↓
Driver Assignment
      ↓
Real-Time Simulation
      ↓
Metrics & Analytics
```

---

# Local Development Setup

## 1. Clone Repository

```bash
git clone <repository-url>
cd spatial_intelligence
```

---

## 2. Create Virtual Environment

```bash
uv venv
source .venv/bin/activate
```

---

## 3. Install Dependencies

```bash
uv sync
```

---

## 4. Run Backend

```bash
uv run uvicorn app.main:app --reload
```

---

# API Endpoints

## Health Check

```http
GET /health
```

---

## Simulation

```http
POST /simulate
GET /scenario
```

---

## Metrics

```http
GET /metrics/{simulation_id}
```

---

# Future Roadmap

* Real-time traffic integration
* Predictive demand modeling
* Reinforcement learning dispatching
* Rider balancing algorithms
* Multi-city support
* Historical analytics
* Live dashboard frontend
* GPU-accelerated spatial rendering

---

# Why This Project Matters

Large logistics companies use sophisticated spatial intelligence systems to optimize delivery operations at scale.

However, many smaller businesses still rely on manual dispatching and intuition.

GeoDispatch AI explores how accessible geospatial technologies can help democratize logistics optimization for local businesses and emerging markets.

---

# Inspiration

This project is inspired by:

* real-world last-mile delivery systems,
* urban logistics optimization,
* GIS analytics platforms,
* and the operational challenges faced by delivery businesses in Nairobi.

---

# Author

Built as a spatial intelligence engineering project exploring the intersection of:

* GIS
* logistics
* optimization
* graph theory
* real-time systems
* and geospatial analytics
