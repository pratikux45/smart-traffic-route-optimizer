"""
Pydantic models for request and response validation.
Designed for Google Maps-style navigation metadata with backward compatibility.
"""

from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


class LocationPoint(BaseModel):
    """Coordinates for a geographic location point."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")


class LocationDetail(BaseModel):
    """Detailed location representation with label."""
    latitude: float
    longitude: float
    label: str = "Location"


class GeocodeResult(BaseModel):
    """Single geocoding search result."""
    display_name: str
    latitude: float
    longitude: float


class GeocodeResponse(BaseModel):
    """Response containing geocoded location results."""
    results: List[GeocodeResult]


class RouteRequest(BaseModel):
    """Route calculation request body."""
    start: LocationPoint
    destination: LocationPoint
    start_label: Optional[str] = None
    destination_label: Optional[str] = None
    preference: Optional[str] = "balanced"  # balanced, fastest, least_signals, shortest


class TrafficSignalPoint(BaseModel):
    """Coordinates and route progression details of a detected traffic signal."""
    id: str
    latitude: float
    longitude: float
    distance_along_route_m: float = 0.0
    estimated_delay_s: float = 45.0
    route_id: str = "route_1"
    name: Optional[str] = None


class RouteScores(BaseModel):
    """Detailed score breakdown across weighted metrics (lower is better)."""
    time: float
    signals: float
    distance: float
    traffic: float
    total: float


class RouteDetail(BaseModel):
    """Individual driving route metrics, geometry, signals, and optimization score."""
    route_id: str = "route_1"
    id: int = 1  # For backward compatibility
    name: str = "Route"
    geometry: Dict[str, Any]  # GeoJSON LineString geometry
    distance_m: float
    duration_s: float
    distance_km: float
    duration_min: float
    duration_minutes: float  # For backward compatibility
    signals: List[TrafficSignalPoint] = []
    traffic_signals: List[TrafficSignalPoint] = []  # For backward compatibility
    signal_count: int
    traffic_signal_count: int  # For backward compatibility
    estimated_signal_delay_s: float
    estimated_signal_delay_min: float
    estimated_signal_delay_minutes: float  # For backward compatibility
    effective_duration_min: float
    scores: RouteScores
    optimization_score: float  # For backward compatibility
    is_optimized: bool = False


class OptimizationMeta(BaseModel):
    """Optimization configuration and decision metadata."""
    optimized_route_id: str
    preference: str = "balanced"
    weights: Dict[str, float]


class ServiceMetadata(BaseModel):
    """Data provider sources."""
    traffic_source: str = "static"
    signal_source: str = "OpenStreetMap"
    routing_source: str = "OSRM"


class RouteResponse(BaseModel):
    """Complete navigation response containing all alternatives, scores, and metadata."""
    source: LocationDetail
    destination: LocationDetail
    routes: List[RouteDetail]
    optimization: OptimizationMeta
    optimized_route_id: Union[str, int]
    metadata: ServiceMetadata
    warning: Optional[str] = None
    disclaimer: str = (
        "Traffic signal timing is estimated. OpenStreetMap provides signal locations, "
        "not live signal phases or queue lengths."
    )


class HealthResponse(BaseModel):
    """Health check endpoint response model."""
    status: str = "ok"
    routing: str = "OSRM"
    geocoding: str = "Nominatim"
    traffic_signals: str = "OpenStreetMap/Overpass"
