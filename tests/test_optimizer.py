"""
Unit tests for Route Optimization scoring, metric normalization, single/multiple routes,
identical metrics, zero-division protection, deterministic tie-breaking, and preferences.
"""

import pytest
from app.services.optimizer import optimize_routes, _normalize, get_weights_for_preference


def test_score_normalization_and_zero_division():
    """Test min-max normalization including identical bounds (zero division protection)."""
    assert _normalize(10.0, 10.0, 20.0) == 0.0
    assert _normalize(20.0, 10.0, 20.0) == 1.0
    assert _normalize(15.0, 10.0, 20.0) == 0.5
    # Edge case: min == max (zero division protection)
    assert _normalize(10.0, 10.0, 10.0) == 0.0
    assert _normalize(500.0, 500.0, 500.0) == 0.0


def test_route_optimization_normal_case():
    """Test standard case with two candidate routes having differing metrics."""
    processed_routes = [
        {
            "id": 1,
            "route_id": "route_1",
            "name": "Route 1 (Longer with more signals)",
            "distance_m": 15000.0,  # 15.0 km
            "duration_s": 1800.0,   # 30.0 min
            "signal_count": 10,
            "estimated_signal_delay_s": 450.0,
            "estimated_signal_delay_min": 7.5,
            "geometry": {"type": "LineString", "coordinates": []},
            "signals": []
        },
        {
            "id": 2,
            "route_id": "route_2",
            "name": "Route 2 (Shorter, faster, fewer signals)",
            "distance_m": 10000.0,  # 10.0 km
            "duration_s": 900.0,    # 15.0 min
            "signal_count": 2,
            "estimated_signal_delay_s": 90.0,
            "estimated_signal_delay_min": 1.5,
            "geometry": {"type": "LineString", "coordinates": []},
            "signals": []
        }
    ]

    routes_out, best_id, meta = optimize_routes(processed_routes, preference="balanced", return_meta=True)

    assert len(routes_out) == 2
    assert best_id == "route_2"

    r2 = next(r for r in routes_out if r.route_id == "route_2")
    r1 = next(r for r in routes_out if r.route_id == "route_1")

    assert r2.is_optimized is True
    assert r1.is_optimized is False
    assert r2.scores.total < r1.scores.total
    assert r2.scores.time <= r1.scores.time


def test_route_optimization_one_route():
    """Test optimizer behavior when only a single route is available."""
    single_route = [
        {
            "id": 1,
            "route_id": "route_1",
            "name": "Single Route",
            "distance_m": 8000.0,
            "duration_s": 720.0,
            "signal_count": 3,
            "estimated_signal_delay_s": 135.0,
            "geometry": {"type": "LineString", "coordinates": []},
            "signals": []
        }
    ]

    routes_out, best_id, meta = optimize_routes(single_route, preference="balanced", return_meta=True)

    assert len(routes_out) == 1
    assert best_id == "route_1"
    assert routes_out[0].is_optimized is True
    # Normalized bounds are 0.0 because min == max; no NaN or errors
    assert not pytest.approx(routes_out[0].scores.total, 0.001) == float("nan")


def test_route_optimization_identical_metrics():
    """Test optimizer handling when multiple routes have identical duration, distance, and signals."""
    identical_routes = [
        {
            "id": 1,
            "route_id": "route_1",
            "name": "Route 1",
            "distance_m": 10000.0,
            "duration_s": 900.0,
            "signal_count": 4,
            "geometry": {"type": "LineString", "coordinates": []},
            "signals": []
        },
        {
            "id": 2,
            "route_id": "route_2",
            "name": "Route 2",
            "distance_m": 10000.0,
            "duration_s": 900.0,
            "signal_count": 4,
            "geometry": {"type": "LineString", "coordinates": []},
            "signals": []
        }
    ]

    routes_out, best_id = optimize_routes(identical_routes, preference="balanced")

    assert len(routes_out) == 2
    # Exactly one route must be is_optimized = True
    optimized_count = sum(1 for r in routes_out if r.is_optimized)
    assert optimized_count == 1


def test_route_optimization_deterministic_tie_breaking():
    """Test deterministic tie-breaking hierarchy: Total Score -> Duration -> Signal Delay -> Distance."""
    # Two routes with identical total scores but route_1 has lower duration
    routes_data = [
        {
            "id": 1,
            "route_id": "route_1",
            "name": "Route A (Faster Duration)",
            "distance_m": 12000.0,
            "duration_s": 800.0,
            "signal_count": 5,
            "geometry": {"type": "LineString", "coordinates": []},
            "signals": []
        },
        {
            "id": 2,
            "route_id": "route_2",
            "name": "Route B (Slower Duration)",
            "distance_m": 12000.0,
            "duration_s": 850.0,
            "signal_count": 5,
            "geometry": {"type": "LineString", "coordinates": []},
            "signals": []
        }
    ]

    routes_out, best_id = optimize_routes(routes_data)
    assert best_id == "route_1"
    assert routes_out[0].route_id == "route_1"
    assert routes_out[0].is_optimized is True


def test_preference_weighting():
    """Test that different preference modes correctly alter metric weights."""
    fastest_weights = get_weights_for_preference("fastest")
    signals_weights = get_weights_for_preference("least_signals")
    shortest_weights = get_weights_for_preference("shortest")

    assert fastest_weights["time"] > fastest_weights["signals"]
    assert signals_weights["signals"] > signals_weights["time"]
    assert shortest_weights["distance"] > shortest_weights["time"]
