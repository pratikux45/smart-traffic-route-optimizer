"""
Application Configuration Module for Smart Traffic Route Optimizer.
Provides centralized settings loaded from environment variables with sensible defaults.
"""

import os
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


class Settings:
    """Application Settings with configurable defaults."""

    # Server Configuration
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # OSRM Driving Routing Service
    OSRM_URL: str = os.getenv("OSRM_URL", "https://router.project-osrm.org").rstrip("/")
    OSRM_TIMEOUT: float = float(os.getenv("OSRM_TIMEOUT", "30.0"))
    MAX_ROUTE_ALTERNATIVES: int = int(os.getenv("MAX_ROUTE_ALTERNATIVES", "3"))
    ROUTE_SIMILARITY_THRESHOLD: float = float(os.getenv("ROUTE_SIMILARITY_THRESHOLD", "0.85"))

    # OpenStreetMap Nominatim Geocoding Service
    NOMINATIM_URL: str = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search").rstrip("/")
    NOMINATIM_TIMEOUT: float = float(os.getenv("NOMINATIM_TIMEOUT", "20.0"))

    # OpenStreetMap Overpass Traffic Signals Service
    OVERPASS_URL: str = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter").rstrip("/")
    OVERPASS_TIMEOUT: float = float(os.getenv("OVERPASS_TIMEOUT", "30.0"))
    OVERPASS_FALLBACK_URLS: List[str] = [
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]

    # Traffic Signal Matching & Delay Parameters
    SIGNAL_MATCH_DISTANCE_METERS: float = float(
        os.getenv("SIGNAL_MATCH_DISTANCE_METERS", os.getenv("SIGNAL_MATCH_THRESHOLD_METERS", "30.0"))
    )
    SIGNAL_MATCH_THRESHOLD_METERS: float = SIGNAL_MATCH_DISTANCE_METERS  # Backward compatibility
    SIGNAL_DEDUP_DISTANCE_METERS: float = float(os.getenv("SIGNAL_DEDUP_DISTANCE_METERS", "10.0"))
    AVERAGE_SIGNAL_DELAY_SECONDS: float = float(os.getenv("AVERAGE_SIGNAL_DELAY_SECONDS", "45.0"))

    # Cache TTL Configurations (seconds)
    GEOCODE_CACHE_TTL: int = int(os.getenv("GEOCODE_CACHE_TTL", "3600"))    # 1 hour
    ROUTE_CACHE_TTL: int = int(os.getenv("ROUTE_CACHE_TTL", "300"))          # 5 minutes
    SIGNAL_CACHE_TTL: int = int(os.getenv("SIGNAL_CACHE_TTL", "3600"))       # 1 hour

    # Route Optimization Default Weights (Must sum to 1.0)
    TIME_WEIGHT: float = float(os.getenv("TIME_WEIGHT", "0.50"))
    SIGNAL_WEIGHT: float = float(os.getenv("SIGNAL_WEIGHT", "0.20"))
    DISTANCE_WEIGHT: float = float(os.getenv("DISTANCE_WEIGHT", "0.20"))
    TRAFFIC_WEIGHT: float = float(os.getenv("TRAFFIC_WEIGHT", "0.10"))

    # HTTP Client Identification
    USER_AGENT: str = os.getenv(
        "USER_AGENT",
        "SmartTrafficRouteOptimizer/2.0 (https://github.com/example/smart-traffic-route-optimizer)"
    )


settings = Settings()
