"""
Integration tests for FastAPI application endpoints (/api/health, /api/geocode, /api/routes).
Tests valid route requests, invalid coordinates, and graceful service failure handling.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.utils.cache import geocode_cache, router_cache, overpass_cache

client = TestClient(app)


def test_health_check_endpoint():
    """Test health check returns 200 with service configuration metadata."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "routing" in data
    assert "geocoding" in data
    assert "traffic_signals" in data


def test_geocode_endpoint_success():
    """Test /api/geocode query returning coordinates."""
    geocode_cache.clear()
    mock_data = [
        {"display_name": "Nagpur Station", "lat": "21.1500", "lon": "79.0800"}
    ]
    mock_resp = MagicMock(status_code=200, json=lambda: mock_data)
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        response = client.get("/api/geocode?q=Nagpur+Station")

    assert response.status_code == 200
    results = response.json().get("results", [])
    assert len(results) == 1
    assert results[0]["display_name"] == "Nagpur Station"


def test_compute_routes_api_valid_request():
    """Test /api/routes calculating driving alternatives, signals, and optimization score."""
    router_cache.clear()
    overpass_cache.clear()

    mock_osrm_data = {
        "code": "Ok",
        "routes": [
            {
                "distance": 12000.0,
                "duration": 900.0,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[79.0800, 21.1500], [79.0500, 21.1550]]
                },
                "legs": [{"summary": "Central Ave"}]
            }
        ]
    }
    mock_osrm_resp = MagicMock(status_code=200, json=lambda: mock_osrm_data)
    mock_osrm_resp.raise_for_status = MagicMock()

    mock_overpass_data = {
        "elements": [
            {"type": "node", "id": "sig_123", "lat": 21.1510, "lon": 79.0700, "tags": {"name": "Central Chowk"}}
        ]
    }
    mock_overpass_resp = MagicMock(status_code=200, json=lambda: mock_overpass_data)
    mock_overpass_resp.raise_for_status = MagicMock()

    payload = {
        "start": {"latitude": 21.1500, "longitude": 79.0800},
        "destination": {"latitude": 21.1550, "longitude": 79.0500},
        "start_label": "Nagpur Station",
        "destination_label": "Futala Lake",
        "preference": "balanced"
    }

    with patch("httpx.AsyncClient.get", return_value=mock_osrm_resp), \
         patch("httpx.AsyncClient.post", return_value=mock_overpass_resp):
        response = client.post("/api/routes", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "source" in data
    assert "destination" in data
    assert "routes" in data
    assert len(data["routes"]) == 1

    route = data["routes"][0]
    assert route["route_id"] == "route_1"
    assert route["is_optimized"] is True
    assert route["signal_count"] >= 0
    assert "scores" in route
    assert "optimization" in data
    assert data["optimization"]["optimized_route_id"] == "route_1"


def test_compute_routes_api_invalid_coordinates():
    """Test validation rejection when coordinates are out of bounds."""
    payload = {
        "start": {"latitude": 999.0, "longitude": 79.0800},  # Invalid latitude
        "destination": {"latitude": 21.1550, "longitude": 79.0500}
    }
    response = client.post("/api/routes", json=payload)
    assert response.status_code == 422  # Pydantic validation error


def test_compute_routes_api_overpass_failure_fallback():
    """Test that when Overpass fails, routes are still returned with a warning banner."""
    router_cache.clear()
    overpass_cache.clear()

    mock_osrm_data = {
        "code": "Ok",
        "routes": [
            {
                "distance": 8000.0,
                "duration": 600.0,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[79.0800, 21.1500], [79.0600, 21.1550]]
                },
                "legs": [{"summary": "Wardha Rd"}]
            }
        ]
    }
    mock_osrm_resp = MagicMock(status_code=200, json=lambda: mock_osrm_data)
    mock_osrm_resp.raise_for_status = MagicMock()

    payload = {
        "start": {"latitude": 21.1500, "longitude": 79.0800},
        "destination": {"latitude": 21.1550, "longitude": 79.0600}
    }

    # Overpass fails with 504 Gateway Timeout
    with patch("httpx.AsyncClient.get", return_value=mock_osrm_resp), \
         patch("httpx.AsyncClient.post", side_effect=Exception("Overpass 504")):
        response = client.post("/api/routes", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert len(data["routes"]) == 1
    assert data["warning"] is not None
    assert "temporarily unavailable" in data["warning"]
