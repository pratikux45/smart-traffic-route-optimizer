"""
Route optimization service scoring driving routes based on multi-metric normalization.
Supports configurable weights, user routing preferences, detailed score breakdown,
and deterministic tie-breaking.
"""

import logging
from typing import List, Dict, Any, Tuple, Union
from app.config import settings
from app.models.route_models import RouteDetail, TrafficSignalPoint, RouteScores, OptimizationMeta

logger = logging.getLogger("smart_traffic_optimizer.optimizer")

# Preset routing preference weights
PREFERENCE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "balanced": {
        "time": settings.TIME_WEIGHT,
        "signals": settings.SIGNAL_WEIGHT,
        "distance": settings.DISTANCE_WEIGHT,
        "traffic": settings.TRAFFIC_WEIGHT,
    },
    "fastest": {
        "time": 0.70,
        "signals": 0.10,
        "distance": 0.15,
        "traffic": 0.05,
    },
    "least_signals": {
        "time": 0.25,
        "signals": 0.55,
        "distance": 0.15,
        "traffic": 0.05,
    },
    "shortest": {
        "time": 0.15,
        "signals": 0.10,
        "distance": 0.70,
        "traffic": 0.05,
    },
}


def _normalize(value: float, min_val: float, max_val: float) -> float:
    """
    Normalize a metric value to [0.0, 1.0] range relative to min and max.
    Zero-division protection: returns 0.0 when min == max.
    """
    if max_val <= min_val or abs(max_val - min_val) < 1e-9:
        return 0.0
    return (value - min_val) / (max_val - min_val)


def get_weights_for_preference(preference: str = "balanced") -> Dict[str, float]:
    """Retrieve and normalize metric weights for a given routing preference."""
    pref_key = preference.lower().strip() if preference else "balanced"
    raw_weights = PREFERENCE_WEIGHTS.get(pref_key, PREFERENCE_WEIGHTS["balanced"])

    total_w = sum(raw_weights.values())
    if total_w <= 0:
        total_w = 1.0

    return {k: round(v / total_w, 4) for k, v in raw_weights.items()}


def optimize_routes(
    processed_routes: List[Dict[str, Any]],
    preference: str = "balanced",
    traffic_factor: float = 0.5,
    return_meta: bool = False
) -> Union[Tuple[List[RouteDetail], Union[str, int]], Tuple[List[RouteDetail], Union[str, int], OptimizationMeta]]:
    """
    Calculate multi-metric optimization scores for candidate driving routes.

    Formula:
      score = w_time * norm(time)
            + w_signals * norm(signals)
            + w_distance * norm(distance)
            + w_traffic * traffic_factor

    Lower score indicates a superior route.
    Deterministically breaks ties by: (1) Total score, (2) Travel duration, (3) Signal delay, (4) Distance.
    """
    if not processed_routes:
        meta = OptimizationMeta(optimized_route_id="", preference=preference, weights={})
        return ([], "", meta) if return_meta else ([], 0)

    weights = get_weights_for_preference(preference)

    # 1. Parse route metrics
    candidates = []
    for r in processed_routes:
        dist_m = float(r.get("distance_m", r.get("distance_meters", 0.0)))
        dur_s = float(r.get("duration_s", r.get("duration_seconds", 0.0)))
        dist_km = round(dist_m / 1000.0, 2)
        dur_min = round(dur_s / 60.0, 1)

        sig_count = int(r.get("signal_count", r.get("traffic_signal_count", 0)))
        delay_s = float(r.get("estimated_signal_delay_s", sig_count * settings.AVERAGE_SIGNAL_DELAY_SECONDS))
        delay_min = round(delay_s / 60.0, 1)

        candidates.append({
            "raw": r,
            "dist_m": dist_m,
            "dur_s": dur_s,
            "dist_km": dist_km,
            "dur_min": dur_min,
            "sig_count": sig_count,
            "delay_s": delay_s,
            "delay_min": delay_min,
            "effective_dur_min": round(dur_min + delay_min, 1)
        })

    # 2. Compute min-max normalization bounds
    min_dur = min(c["dur_s"] for c in candidates)
    max_dur = max(c["dur_s"] for c in candidates)

    min_dist = min(c["dist_m"] for c in candidates)
    max_dist = max(c["dist_m"] for c in candidates)

    min_sig = min(c["sig_count"] for c in candidates)
    max_sig = max(c["sig_count"] for c in candidates)

    # 3. Calculate score breakdowns
    scored_items = []
    for item in candidates:
        raw = item["raw"]
        norm_time = _normalize(item["dur_s"], min_dur, max_dur)
        norm_dist = _normalize(item["dist_m"], min_dist, max_dist)
        norm_sig = _normalize(item["sig_count"], min_sig, max_sig)

        time_score = round(weights["time"] * norm_time, 3)
        signal_score = round(weights["signals"] * norm_sig, 3)
        distance_score = round(weights["distance"] * norm_dist, 3)
        traffic_score = round(weights["traffic"] * traffic_factor, 3)
        total_score = round(time_score + signal_score + distance_score + traffic_score, 3)

        scores = RouteScores(
            time=time_score,
            signals=signal_score,
            distance=distance_score,
            traffic=traffic_score,
            total=total_score
        )

        # Reconstruct signal objects
        raw_signals = raw.get("signals", raw.get("traffic_signals", []))
        signals = [
            s if isinstance(s, TrafficSignalPoint) else TrafficSignalPoint(**s)
            for s in raw_signals
        ]

        route_id_str = str(raw.get("route_id", f"route_{raw.get('id', 1)}"))
        int_id = int(raw.get("id", 1))

        route_detail = RouteDetail(
            route_id=route_id_str,
            id=int_id,
            name=raw.get("name", f"Route {int_id}"),
            geometry=raw.get("geometry", {}),
            distance_m=item["dist_m"],
            duration_s=item["dur_s"],
            distance_km=item["dist_km"],
            duration_min=item["dur_min"],
            duration_minutes=item["dur_min"],
            signals=signals,
            traffic_signals=signals,
            signal_count=item["sig_count"],
            traffic_signal_count=item["sig_count"],
            estimated_signal_delay_s=item["delay_s"],
            estimated_signal_delay_min=item["delay_min"],
            estimated_signal_delay_minutes=item["delay_min"],
            effective_duration_min=item["effective_dur_min"],
            scores=scores,
            optimization_score=total_score,
            is_optimized=False,
        )

        scored_items.append((route_detail, item))

    # 4. Deterministic tie-breaking
    # Sort order: (1) Total score, (2) Travel duration, (3) Signal delay, (4) Distance
    scored_items.sort(key=lambda pair: (
        round(pair[0].scores.total, 4),
        pair[1]["dur_s"],
        pair[1]["delay_s"],
        pair[1]["dist_m"]
    ))

    # Mark top route as optimized
    scored_items[0][0].is_optimized = True
    best_route = scored_items[0][0]
    best_route_id = best_route.route_id

    # For backward compatibility where callers expect int ID if routes had int id:
    legacy_best_id = best_route.id

    logger.info(
        f"[OPTIMIZER] Selected {best_route.route_id} ({best_route.name}) with score {best_route.scores.total} (preference: {preference})"
    )

    final_routes = [pair[0] for pair in scored_items]

    meta = OptimizationMeta(
        optimized_route_id=best_route_id,
        preference=preference,
        weights=weights
    )

    if return_meta:
        return final_routes, best_route_id, meta
    return final_routes, best_route_id
