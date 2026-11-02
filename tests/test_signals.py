"""
Unit tests for Traffic Signal Detection, Spatial Matching, Duplicate Removal,
Multi-route Isolation, Driving Order Progression, and Overpass Fallbacks.
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock
from app.services.traffic_signals import (
    match_signals_to_route,
    process_route_traffic_signals,
)
from app.utils.cache import overpass_cache


def test_signals_near_and_far_from_route():
    """Test that signals within threshold are matched and signals far from route are excluded."""
    # Polyline along latitude 21.0000
    route_coords = [
        [79.0000, 21.0000],
        [79.0050, 21.0000],
        [79.0100, 21.0000]
    ]

    candidate_nodes = [
        # Signal Near (distance ~0m)
        {"id": "sig_near", "latitude": 21.0000, "longitude": 79.0030, "name": "Near Signal"},
        # Signal Far (distance ~300m)
        {"id": "sig_far", "latitude": 21.0030, "longitude": 79.0050, "name": "Far Signal"},
    ]

    matched = match_signals_to_route(route_coords, candidate_nodes, route_id="route_1", threshold_meters=30.0)

    assert len(matched) == 1
    assert matched[0].id == "sig_near"
    assert matched[0].name == "Near Signal"
    assert matched[0].route_id == "route_1"


def test_duplicate_signal_deduplication():
    """Test deduplication of close signals (< 10m) representing the same intersection."""
    route_coords = [
        [79.0000, 21.0000],
        [79.0100, 21.0000]
    ]

    candidate_nodes = [
        {"id": "node_1", "latitude": 21.0000, "longitude": 79.0050, "name": "Junction Main"},
        {"id": "node_2", "latitude": 21.00002, "longitude": 79.00502, "name": "Junction Opposite Pole"},  # ~3m away
    ]

    matched = match_signals_to_route(route_coords, candidate_nodes, route_id="route_1", dedup_distance_meters=10.0)
    assert len(matched) == 1
    assert matched[0].id == "node_1"


def test_signal_driving_order_sorting():
    """Test that signals along the route are sorted in driving order from origin to destination."""
    route_coords = [
        [79.0000, 21.0000],
        [79.0050, 21.0000],
        [79.0100, 21.0000]
    ]

    # Provide candidate nodes out of order
    candidate_nodes = [
        {"id": "sig_3", "latitude": 21.0000, "longitude": 79.0080, "name": "Signal 3 (800m)"},
        {"id": "sig_1", "latitude": 21.0000, "longitude": 79.0020, "name": "Signal 1 (200m)"},
        {"id": "sig_2", "latitude": 21.0000, "longitude": 79.0050, "name": "Signal 2 (500m)"},
    ]

    matched = match_signals_to_route(route_coords, candidate_nodes, route_id="route_1")

    assert len(matched) == 3
    assert [s.id for s in matched] == ["sig_1", "sig_2", "sig_3"]
    assert matched[0].distance_along_route_m < matched[1].distance_along_route_m < matched[2].distance_along_route_m


def test_signal_matching_multiple_routes_independently():
    """Test that signals are matched to specific route geometries independently and not spilled over."""
    # Route A goes East along lat 21.0000
    route_a_coords = [[79.0000, 21.0000], [79.0100, 21.0000]]
    # Route B goes North along lon 79.0000
    route_b_coords = [[79.0000, 21.0000], [79.0000, 21.0100]]

    candidate_nodes = [
        {"id": "sig_a", "latitude": 21.0000, "longitude": 79.0050, "name": "East Signal"},
        {"id": "sig_b", "latitude": 21.0050, "longitude": 79.0000, "name": "North Signal"},
    ]

    matched_a = match_signals_to_route(route_a_coords, candidate_nodes, route_id="route_1")
    matched_b = match_signals_to_route(route_b_coords, candidate_nodes, route_id="route_2")

    assert len(matched_a) == 1
    assert matched_a[0].id == "sig_a"
    assert matched_a[0].route_id == "route_1"

    assert len(matched_b) == 1
    assert matched_b[0].id == "sig_b"
    assert matched_b[0].route_id == "route_2"


def test_process_route_traffic_signals_delay_calculation():
    """Test delay formula: signal_count * AVERAGE_SIGNAL_DELAY_SECONDS (45s)."""
    overpass_cache.clear()

    raw_routes = [
        {
            "id": 1,
            "route_id": "route_1",
            "name": "Route 1",
            "distance_m": 10000.0,
            "duration_s": 600.0,
            "geometry": {
                "type": "LineString",
                "coordinates": [[79.0000, 21.0000], [79.0100, 21.0000]]
            }
        }
    ]

    mock_overpass_elements = {
        "elements": [
            {"type": "node", "id": 1, "lat": 21.0000, "lon": 79.0030},
            {"type": "node", "id": 2, "lat": 21.0000, "lon": 79.0070},
        ]
    }

    mock_httpx_response = MagicMock()
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_overpass_elements
    mock_httpx_response.raise_for_status = MagicMock()

    async def _run():
        with patch("httpx.AsyncClient.post", return_value=mock_httpx_response):
            return await process_route_traffic_signals(raw_routes)

    updated_routes, success = asyncio.run(_run())

    assert success is True
    assert len(updated_routes) == 1
    assert updated_routes[0]["signal_count"] == 2
    # 2 signals * 45s = 90s = 1.5 minutes
    assert pytest.approx(updated_routes[0]["estimated_signal_delay_s"], 0.1) == 90.0
    assert pytest.approx(updated_routes[0]["estimated_signal_delay_min"], 0.1) == 1.5


def test_overpass_failure_fallback():
    """Test graceful fallback when Overpass API fails or times out."""
    overpass_cache.clear()

    raw_routes = [
        {
            "id": 1,
            "route_id": "route_1",
            "name": "Route 1",
            "distance_m": 5000.0,
            "duration_s": 300.0,
            "geometry": {
                "type": "LineString",
                "coordinates": [[79.0000, 21.0000], [79.0050, 21.0000]]
            }
        }
    ]

    async def _run():
        with patch("httpx.AsyncClient.post", side_effect=Exception("Overpass 504 Gateway Timeout")):
            return await process_route_traffic_signals(raw_routes)

    updated_routes, success = asyncio.run(_run())

    assert success is False
    assert len(updated_routes) == 1
    assert updated_routes[0]["signal_count"] == 0
    assert updated_routes[0]["estimated_signal_delay_min"] == 0.0
