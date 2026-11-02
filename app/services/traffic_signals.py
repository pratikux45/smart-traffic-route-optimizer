"""
Traffic signal detection service querying OpenStreetMap data via Overpass API.
Matches, deduplicates, and sorts traffic signals along individual route polylines in driving order.
"""

import logging
from typing import List, Dict, Any, Tuple
import httpx

from app.config import settings
from app.models.route_models import TrafficSignalPoint
from app.utils.cache import overpass_cache
from app.utils.geometry import (
    calculate_bounding_box,
    min_distance_to_polyline,
    haversine_distance,
    calculate_distance_along_route,
)

logger = logging.getLogger("smart_traffic_optimizer.signals")


async def fetch_traffic_signals_for_bbox(south: float, west: float,
                                         north: float, east: float) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Query Overpass API for all highway=traffic_signals nodes inside a bounding box.
    Implements in-memory TTL caching and fallback endpoints.
    Returns (list_of_nodes, success_flag).
    """
    cache_key = f"overpass_bbox:{round(south, 3)},{round(west, 3)},{round(north, 3)},{round(east, 3)}"
    cached_data = overpass_cache.get(cache_key)
    if cached_data is not None:
        logger.info("[SIGNALS] Returning cached Overpass signal data")
        return cached_data, True

    overpass_query = f"""
    [out:json][timeout:{int(settings.OVERPASS_TIMEOUT)}];
    node["highway"="traffic_signals"]({south},{west},{north},{east});
    out body;
    """

    headers = {
        "User-Agent": settings.USER_AGENT
    }

    endpoints = [settings.OVERPASS_URL] + settings.OVERPASS_FALLBACK_URLS

    for endpoint in endpoints:
        try:
            logger.info(f"[SIGNALS] Querying Overpass at {endpoint}...")
            async with httpx.AsyncClient(timeout=settings.OVERPASS_TIMEOUT) as client:
                response = await client.post(
                    endpoint,
                    data={"data": overpass_query},
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
                elements = data.get("elements", [])

                nodes = []
                for el in elements:
                    if el.get("type") == "node" and "lat" in el and "lon" in el:
                        tags = el.get("tags", {})
                        name = tags.get("name") or tags.get("description")
                        nodes.append({
                            "id": str(el.get("id", "")),
                            "latitude": float(el["lat"]),
                            "longitude": float(el["lon"]),
                            "name": name,
                        })

                logger.info(f"[SIGNALS] Overpass returned {len(nodes)} candidate signals in bounding box")
                overpass_cache.set(cache_key, nodes)
                return nodes, True

        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.warning(f"[SIGNALS] Overpass endpoint {endpoint} failed: {str(exc)}. Trying next fallback...")
            continue
        except Exception as exc:
            logger.warning(f"[SIGNALS] Unexpected error connecting to {endpoint}: {str(exc)}. Trying next fallback...")
            continue

    logger.warning("[SIGNALS] All Overpass API endpoints failed or timed out. Falling back gracefully.")
    return [], False


def match_signals_to_route(route_coords: List[List[float]],
                           candidate_nodes: List[Dict[str, Any]],
                           route_id: str = "route_1",
                           threshold_meters: float = 30.0,
                           dedup_distance_meters: float = 10.0) -> List[TrafficSignalPoint]:
    """
    Match candidate traffic signals to a route polyline geometry.
    - Only signals within threshold_meters of the route are matched.
    - Deduplicates clustered signals within dedup_distance_meters.
    - Computes distance_along_route_m from origin for each signal.
    - Sorts signals in progressive driving order (origin -> destination).
    """
    matched: List[TrafficSignalPoint] = []

    for node in candidate_nodes:
        lat = node["latitude"]
        lon = node["longitude"]

        # Calculate minimum distance from node to polyline
        dist = min_distance_to_polyline(lat, lon, route_coords)
        if dist <= threshold_meters:
            # Check for duplicate signals already matched nearby
            is_dup = False
            for existing in matched:
                if haversine_distance(lat, lon, existing.latitude, existing.longitude) < dedup_distance_meters:
                    is_dup = True
                    break

            if not is_dup:
                # Compute distance along driving route from start
                dist_along = calculate_distance_along_route(lat, lon, route_coords)

                matched.append(TrafficSignalPoint(
                    id=str(node.get("id", "")),
                    latitude=lat,
                    longitude=lon,
                    distance_along_route_m=dist_along,
                    estimated_delay_s=settings.AVERAGE_SIGNAL_DELAY_SECONDS,
                    route_id=route_id,
                    name=node.get("name")
                ))

    # Sort signals in driving order from start to finish
    matched.sort(key=lambda s: s.distance_along_route_m)
    return matched


async def process_route_traffic_signals(routes_raw: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Process traffic signal detection for a set of raw routes.
    Adds 'traffic_signals', 'signals', 'signal_count', 'estimated_signal_delay_s',
    and 'estimated_signal_delay_min' to each route.
    Returns (updated_routes, overpass_success_flag).
    """
    if not routes_raw:
        return [], True

    # 1. Gather geometries across all routes
    geometries = [r.get("geometry", {}).get("coordinates", []) for r in routes_raw]

    # 2. Compute overall bounding box with margin
    south, west, north, east = calculate_bounding_box(geometries, margin_degrees=0.015)

    # 3. Query Overpass API once for the combined bounding box
    candidate_nodes, success = await fetch_traffic_signals_for_bbox(south, west, north, east)

    # 4. Spatially match signals to EACH individual route
    updated_routes = []
    for r in routes_raw:
        coords = r.get("geometry", {}).get("coordinates", [])
        route_id = r.get("route_id", f"route_{r.get('id', 1)}")

        if success and candidate_nodes:
            matched = match_signals_to_route(
                coords,
                candidate_nodes,
                route_id=route_id,
                threshold_meters=settings.SIGNAL_MATCH_DISTANCE_METERS,
                dedup_distance_meters=settings.SIGNAL_DEDUP_DISTANCE_METERS
            )
        else:
            matched = []

        sig_count = len(matched)
        delay_seconds = round(sig_count * settings.AVERAGE_SIGNAL_DELAY_SECONDS, 1)
        delay_minutes = round(delay_seconds / 60.0, 1)

        logger.info(f"[SIGNALS] {route_id}: {sig_count} signals detected (~{delay_minutes} min delay)")

        r_copy = dict(r)
        r_copy["signals"] = matched
        r_copy["traffic_signals"] = matched  # Backward compatibility
        r_copy["signal_count"] = sig_count
        r_copy["traffic_signal_count"] = sig_count  # Backward compatibility
        r_copy["estimated_signal_delay_s"] = delay_seconds
        r_copy["estimated_signal_delay_min"] = delay_minutes
        r_copy["estimated_signal_delay_minutes"] = delay_minutes  # Backward compatibility
        updated_routes.append(r_copy)

    return updated_routes, success
