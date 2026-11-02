"""
Unit tests for Geocoder service (Nominatim parser, caching, empty queries, and timeout).
"""

import asyncio
import pytest
import httpx
from unittest.mock import patch, MagicMock
from app.services.geocoder import geocode_location
from app.utils.cache import geocode_cache


def test_geocode_location_success():
    """Test parsing of Nominatim geocoding response."""
    geocode_cache.clear()

    mock_response_data = [
        {
            "display_name": "Nagpur, Maharashtra, India",
            "lat": "21.1458",
            "lon": "79.0882",
        },
        {
            "display_name": "Nagpur District, Maharashtra, India",
            "lat": "21.1500",
            "lon": "79.0900",
        }
    ]

    mock_httpx_response = MagicMock()
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_response_data
    mock_httpx_response.raise_for_status = MagicMock()

    async def _run():
        with patch("httpx.AsyncClient.get", return_value=mock_httpx_response):
            return await geocode_location("Nagpur")

    results = asyncio.run(_run())

    assert len(results) == 2
    assert results[0].display_name == "Nagpur, Maharashtra, India"
    assert round(results[0].latitude, 4) == 21.1458
    assert round(results[0].longitude, 4) == 79.0882


def test_geocode_location_empty_query():
    """Test geocoding with empty query string returns empty list immediately."""
    results = asyncio.run(geocode_location("   "))
    assert results == []


def test_geocode_location_caching():
    """Test geocoding caching prevents duplicate outbound HTTP requests."""
    geocode_cache.clear()

    mock_response_data = [
        {
            "display_name": "Futala Lake, Nagpur",
            "lat": "21.1550",
            "lon": "79.0480",
        }
    ]

    mock_httpx_response = MagicMock()
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_response_data
    mock_httpx_response.raise_for_status = MagicMock()

    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_httpx_response

    async def _run():
        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            res1 = await geocode_location("Futala Lake")
            res2 = await geocode_location("Futala Lake")
            return res1, res2

    res1, res2 = asyncio.run(_run())
    assert len(res1) == 1
    assert len(res2) == 1
    assert res1[0].display_name == res2[0].display_name
    assert call_count == 1  # Second query retrieved from cache


def test_geocode_location_timeout():
    """Test handling of Nominatim HTTP timeout."""
    geocode_cache.clear()

    async def _run():
        with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Timeout")):
            return await geocode_location("Timeout City")

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(_run())
    assert "timed out" in str(exc_info.value).lower()
