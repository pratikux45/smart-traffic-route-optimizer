"""
FastAPI Main Application Module for Smart Traffic Route Optimizer.
Provides robust driving route generation, traffic signal detection, and multi-metric optimization.
"""

import os
import time
import logging
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.route_models import (
    HealthResponse,
    GeocodeResponse,
    RouteRequest,
    RouteResponse,
    LocationDetail,
    OptimizationMeta,
    ServiceMetadata,
)
from app.services.geocoder import geocode_location
from app.services.router import fetch_osrm_routes
from app.services.traffic_signals import process_route_traffic_signals
from app.services.optimizer import optimize_routes
from app.services.traffic_provider import get_default_traffic_provider

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("smart_traffic_optimizer")

app = FastAPI(
    title="Smart Traffic Route Optimizer",
    description="Free open-source route optimization using OpenStreetMap, OSRM, and Overpass API.",
    version="2.0.0"
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve path to frontend directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", response_class=FileResponse, include_in_schema=False)
async def serve_index():
    """Serve main frontend SPA application."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    return FileResponse(index_path)


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Return health status and active data provider configurations."""
    return HealthResponse(
        status="ok",
        routing=f"OSRM ({settings.OSRM_URL})",
        geocoding=f"Nominatim ({settings.NOMINATIM_URL})",
        traffic_signals=f"OpenStreetMap/Overpass ({settings.OVERPASS_URL})"
    )


@app.get("/api/geocode", response_model=GeocodeResponse)
async def geocode(q: str = Query(..., min_length=1, description="Location search query")):
    """Convert location search query to latitude and longitude coordinates."""
    try:
        results = await geocode_location(q)
        return GeocodeResponse(results=results)
    except Exception as exc:
        logger.error(f"[GEOCODE] Error resolving location '{q}': {str(exc)}")
        raise HTTPException(
            status_code=500,
            detail="Unable to resolve location. Please check your query or try again later."
        )


@app.post("/api/routes", response_model=RouteResponse)
async def compute_routes(request: RouteRequest):
    """
    Calculate and optimize driving routes between start and destination coordinates.
    Integrates OSRM driving geometry, Overpass traffic signals, and multi-metric optimization scoring.
    """
    start_time = time.time()
    logger.info(
        f"[ROUTES] New request: ({request.start.latitude}, {request.start.longitude}) -> "
        f"({request.destination.latitude}, {request.destination.longitude}) [pref: {request.preference}]"
    )

    try:
        # 1. Fetch driving routes from OSRM
        raw_routes = await fetch_osrm_routes(
            start_lat=request.start.latitude,
            start_lon=request.start.longitude,
            dest_lat=request.destination.latitude,
            dest_lon=request.destination.longitude,
        )

        if not raw_routes:
            raise HTTPException(
                status_code=404,
                detail="No driving routes found between the selected locations. Please verify coordinates."
            )

        logger.info(f"[ROUTES] {len(raw_routes)} candidate routes received from OSRM")

        # 2. Process traffic signal data via Overpass API with graceful fallback
        processed_routes, overpass_success = await process_route_traffic_signals(raw_routes)

        # 3. Obtain traffic factor from traffic provider abstraction
        traffic_provider = get_default_traffic_provider()
        sample_geometry = raw_routes[0].get("geometry", {}).get("coordinates", [])
        traffic_factor = await traffic_provider.get_traffic_factor(sample_geometry)

        # 4. Calculate optimization scores and identify top route
        route_details, optimized_id, opt_meta = optimize_routes(
            processed_routes,
            preference=request.preference or "balanced",
            traffic_factor=traffic_factor,
            return_meta=True
        )

        total_elapsed = round(time.time() - start_time, 2)
        logger.info(f"[TIMING] Total processing completed in {total_elapsed}s. Optimized: {optimized_id}")

        warning_msg = None
        if not overpass_success:
            warning_msg = "Traffic signal data is temporarily unavailable. Routes calculated using baseline estimates."

        start_label = request.start_label or f"({round(request.start.latitude, 4)}, {round(request.start.longitude, 4)})"
        dest_label = request.destination_label or f"({round(request.destination.latitude, 4)}, {round(request.destination.longitude, 4)})"

        return RouteResponse(
            source=LocationDetail(
                latitude=request.start.latitude,
                longitude=request.start.longitude,
                label=start_label
            ),
            destination=LocationDetail(
                latitude=request.destination.latitude,
                longitude=request.destination.longitude,
                label=dest_label
            ),
            routes=route_details,
            optimization=opt_meta,
            optimized_route_id=optimized_id,
            metadata=ServiceMetadata(
                traffic_source=traffic_provider.get_metadata().get("traffic_source", "static"),
                signal_source="OpenStreetMap",
                routing_source="OSRM"
            ),
            warning=warning_msg,
            disclaimer="Traffic signal timing is estimated. OpenStreetMap provides signal locations, not live signal phases or queue lengths."
        )

    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.error(f"[ROUTES] Runtime error during calculation: {str(exc)}")
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"[ROUTES] Unexpected error: {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to retrieve routes. Please try again.")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler ensuring tracebacks are never exposed to clients."""
    logger.error(f"Unhandled exception at {request.url}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected internal error occurred. Please try again."}
    )
