# Setup Guide - Smart Traffic Route Optimizer

This guide details setting up and executing the application on Windows, Linux, and macOS environments.

---

## 1. Directory Structure Overview

```
smart-traffic-route-optimizer/
│
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application & REST endpoints
│   ├── config.py            # Environment settings & sensible defaults
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── geocoder.py      # OSM Nominatim geocoding client
│   │   ├── router.py        # OSRM driving route engine
│   │   ├── traffic_signals.py# OSM Overpass traffic signal matcher
│   │   └── optimizer.py     # Multi-metric route scoring algorithm
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── route_models.py  # Pydantic request & response schemas
│   │
│   └── utils/
│       ├── __init__.py
│       ├── geometry.py      # Spatial math & distance calculations
│       └── cache.py         # Thread-safe TTL cache
│
├── frontend/
│   ├── index.html           # Modern dashboard HTML5 template
│   ├── style.css            # Dark theme CSS design system
│   └── app.js               # Leaflet map & frontend interaction script
│
├── tests/
│   ├── __init__.py
│   ├── test_geocoder.py
│   ├── test_router.py
│   ├── test_signals.py
│   └── test_optimizer.py
│
├── requirements.txt         # Python package dependencies
├── .env.example             # Optional environment variable template
├── .gitignore               # Git exclude file
├── README.md                # General documentation
└── SETUP.md                 # Step-by-step setup guide
```

---

## 2. Windows Installation (Step-by-Step)

### Step A: Open Terminal / Command Prompt
Navigate to the project root directory:
```powershell
cd smart-traffic-route-optimizer
```

### Step B: Create Python Virtual Environment
```powershell
python -m venv .venv
```

### Step C: Activate Virtual Environment
```powershell
.venv\Scripts\activate
```
*(If PowerShell displays an ExecutionPolicy error, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first).*

### Step D: Upgrade Pip & Install Requirements
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Running the Server

Start the Uvicorn web server:
```powershell
python -m uvicorn app.main:app --reload --port 8000
```

Once running, access the web UI in your browser at:
`http://127.0.0.1:8000`

---

## 4. Running Unit Tests

To run the automated unit test suite:
```powershell
pytest -v
```

All unit tests use mock HTTP responses and complete in under 2 seconds without requiring internet connectivity.
