"""
Unit tests for Router service (OSRM parsing, multiple routes, malformed responses, deduplication, and timeouts).
"""

import asyncio
import pytest
import httpx
from unittest.mock import patch, MagicMock
from app.services.router import fetch_osrm_routes, deduplicate_routes
from app.utils.cache import router_cache


def test_fetch_osrm_routes_success():
    """Test parsing of OSRM routing API response including distance and duration."""
    router_cache.clear()

    mock_osrm_data = {
        "code": "Ok",
        "routes": [
            {
                "distance": 14200.5,  # 14.2 km
                "duration": 1860.0,   # 31 minutes (1860s)
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[79.0882, 21.1458], [79.0576, 21.2716]]
                },
                "legs": [{"summary": "NH44"}]
            },
            {
                "distance": 16100.0,  # 16.1 km
                "duration": 1620.0,   # 27 minutes (1620s)
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[79.0882, 21.1458], [79.0600, 21.2000], [79.0576, 21.2716]]
                },
                "legs": [{"summary": "Ring Road"}]
            }
        ]
    }

    mock_httpx_response = MagicMock()
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_osrm_data
    mock_httpx_response.raise_for_status = MagicMock()

    async def _run():
        with patch("httpx.AsyncClient.get", return_value=mock_httpx_response):
            return await fetch_osrm_routes(21.1458, 79.0882, 21.2716, 79.0576)

    routes = asyncio.run(_run())

    assert len(routes) == 2
    assert routes[0]["id"] == 1
    assert routes[0]["route_id"] == "route_1"
    assert "NH44" in routes[0]["name"]
    assert pytest.approx(routes[0]["distance_m"], 0.1) == 14200.5
    assert pytest.approx(routes[0]["duration_s"], 0.1) == 1860.0
    assert pytest.approx(routes[0]["distance_km"], 0.01) == 14.2
    assert pytest.approx(routes[0]["duration_min"], 0.1) == 31.0
    assert routes[0]["geometry"]["type"] == "LineString"


def test_fetch_osrm_routes_no_routes():
    """Test handling when OSRM returns no routes."""
    router_cache.clear()

    mock_osrm_data = {
        "code": "NoRoute",
        "routes": []
    }

    mock_httpx_response = MagicMock()
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_osrm_data
    mock_httpx_response.raise_for_status = MagicMock()

    async def _run():
        with patch("httpx.AsyncClient.get", return_value=mock_httpx_response):
            return await fetch_osrm_routes(21.1458, 79.0882, 21.2716, 79.0576)

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(_run())
    assert "No driving routes found" in str(exc_info.value)


def test_fetch_osrm_routes_malformed_response():
    """Test rejection of malformed routes with missing or invalid metrics/geometry."""
    router_cache.clear()

    mock_osrm_data = {
        "code": "Ok",
        "routes": [
            {
                "distance": -5.0,  # Invalid negative distance
                "duration": 100.0,
                "geometry": {"coordinates": [[79.0, 21.0], [79.1, 21.1]]}
            },
            {
                "distance": 5000.0,
                "duration": 300.0,
                "geometry": {"coordinates": []}  # Invalid empty geometry
            }
        ]
    }

    mock_httpx_response = MagicMock()
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_osrm_data
    mock_httpx_response.raise_for_status = MagicMock()

    async def _run():
        with patch("httpx.AsyncClient.get", return_value=mock_httpx_response):
            return await fetch_osrm_routes(21.1458, 79.0882, 21.2716, 79.0576)

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(_run())
    assert "malformed" in str(exc_info.value).lower()


def test_deduplicate_routes_exact_duplicate():
    """Test deduplication drops near-identical duplicate routes and preserves distinct routes."""
    identical_coords = [[79.0000, 21.0000], [79.0050, 21.0050], [79.0100, 21.0100]]

    raw_candidates = [
        {
            "id": 1,
            "distance": 10000.0,
            "duration": 600.0,
            "geometry": {"type": "LineString", "coordinates": identical_coords}
        },
        {
            "id": 2,
            "distance": 10050.0,
            "duration": 620.0,
            "geometry": {"type": "LineString", "coordinates": identical_coords}  # Duplicate!
        },
        {
            "id": 3,
            "distance": 14000.0,
            "duration": 700.0,
            "geometry": {
                "type": "LineString",
                "coordinates": [[79.0000, 21.0000], [79.0200, 21.0020], [79.0100, 21.0100]]  # Distinct detour!
            }
        }
    ]

    deduped = deduplicate_routes(raw_candidates, similarity_threshold=0.85)
    assert len(deduped) == 2


def test_fetch_osrm_routes_timeout():
    """Test handling of OSRM request timeout."""
    router_cache.clear()

    async def _run():
        with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("OSRM Timeout")):
            return await fetch_osrm_routes(21.1458, 79.0882, 21.2716, 79.0576)

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(_run())
    assert "timed out" in str(exc_info.value).lower()
