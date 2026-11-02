"""
OSRM Routing service for driving route generation, validation, and geometric deduplication.
"""

import logging
from typing import List, Dict, Any
import httpx

from app.config import settings
from app.utils.cache import router_cache
from app.utils.geometry import calculate_route_similarity

logger = logging.getLogger("smart_traffic_optimizer.router")


def _is_valid_route(route: Dict[str, Any]) -> bool:
    """Validate that an OSRM route object contains valid metrics and geometry."""
    distance = route.get("distance")
    duration = route.get("duration")
    geometry = route.get("geometry")

    if distance is None or duration is None or not geometry:
        return False

    try:
        dist_val = float(distance)
        dur_val = float(duration)
        if dist_val <= 0 or dur_val <= 0:
            return False
    except (ValueError, TypeError):
        return False

    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        return False

    # Check first and last coordinate
    for pt in [coords[0], coords[-1]]:
        if not isinstance(pt, list) or len(pt) < 2:
            return False
        if not (isinstance(pt[0], (int, float)) and isinstance(pt[1], (int, float))):
            return False

    return True


async def _query_osrm(client: httpx.AsyncClient, url: str, params: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Helper to query OSRM with fallback from numeric alternatives to boolean if needed."""
    try:
        response = await client.get(url, params=params, headers=headers)
        if response.status_code == 400 and str(params.get("alternatives")) not in ("true", "false"):
            # Some older/custom OSRM versions require boolean 'true'
            fallback_params = dict(params)
            fallback_params["alternatives"] = "true"
            response = await client.get(url, params=fallback_params, headers=headers)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        logger.error(f"[ROUTES] OSRM HTTP error {exc.response.status_code}: {exc.response.text[:200]}")
        raise RuntimeError(f"Routing service returned HTTP status {exc.response.status_code}.")


def deduplicate_routes(raw_routes: List[Dict[str, Any]],
                       similarity_threshold: float = 0.85) -> List[Dict[str, Any]]:
    """
    Remove route alternatives that are effectively duplicates of another route.
    If two routes share more than the configured similarity threshold and do NOT have
    a meaningful difference in distance or duration (>15%), the faster route is retained.
    """
    if len(raw_routes) <= 1:
        return raw_routes

    unique_routes: List[Dict[str, Any]] = []

    for candidate in raw_routes:
        c_coords = candidate.get("geometry", {}).get("coordinates", [])
        c_dist = float(candidate.get("distance", 0.0))
        c_dur = float(candidate.get("duration", 0.0))
        is_duplicate = False

        for idx, existing in enumerate(unique_routes):
            e_coords = existing.get("geometry", {}).get("coordinates", [])
            e_dist = float(existing.get("distance", 0.0))
            e_dur = float(existing.get("duration", 0.0))

            similarity = calculate_route_similarity(c_coords, e_coords)

            if similarity >= similarity_threshold:
                # Check for meaningful distance/duration variation (>15%)
                dist_diff_ratio = abs(c_dist - e_dist) / max(1.0, e_dist)
                dur_diff_ratio = abs(c_dur - e_dur) / max(1.0, e_dur)

                if dist_diff_ratio < 0.15 and dur_diff_ratio < 0.15:
                    logger.info(
                        f"[ROUTES] Duplicate route identified (similarity={similarity:.2f} >= {similarity_threshold:.2f}, "
                        f"dist_diff={dist_diff_ratio:.1%}, dur_diff={dur_diff_ratio:.1%})."
                    )
                    is_duplicate = True
                    # If candidate is faster than existing, replace existing
                    if c_dur < e_dur:
                        unique_routes[idx] = candidate
                    break

        if not is_duplicate:
            unique_routes.append(candidate)

    return unique_routes


async def fetch_osrm_routes(start_lat: float, start_lon: float,
                            dest_lat: float, dest_lon: float) -> List[Dict[str, Any]]:
    """
    Fetch driving routes from OSRM routing API.
    Validates coordinates, handles retries, deduplicates near-identical alternatives,
    and returns genuine candidate driving routes with stable IDs.
    """
    # Coordinate sanity check
    if not (-90.0 <= start_lat <= 90.0 and -180.0 <= start_lon <= 180.0):
        raise RuntimeError("Invalid origin coordinates.")
    if not (-90.0 <= dest_lat <= 90.0 and -180.0 <= dest_lon <= 180.0):
        raise RuntimeError("Invalid destination coordinates.")

    cache_key = f"osrm:{round(start_lat, 4)},{round(start_lon, 4)}->{round(dest_lat, 4)},{round(dest_lon, 4)}"
    cached_routes = router_cache.get(cache_key)
    if cached_routes is not None:
        logger.info("[ROUTES] Returning cached OSRM route data")
        return cached_routes

    # OSRM expects: longitude,latitude
    coordinates_str = f"{start_lon},{start_lat};{dest_lon},{dest_lat}"
    url = f"{settings.OSRM_URL}/route/v1/driving/{coordinates_str}"

    alt_param = str(settings.MAX_ROUTE_ALTERNATIVES) if settings.MAX_ROUTE_ALTERNATIVES > 1 else "true"
    params = {
        "alternatives": alt_param,
        "overview": "full",
        "geometries": "geojson",
        "steps": "false",
    }

    headers = {
        "User-Agent": settings.USER_AGENT
    }

    logger.info(f"[ROUTES] Querying OSRM: ({start_lat}, {start_lon}) -> ({dest_lat}, {dest_lon})")

    # Retry loop with backoff (up to 2 attempts)
    max_retries = 2
    last_error: Exception = None

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.OSRM_TIMEOUT) as client:
                data = await _query_osrm(client, url, params, headers)

                if data.get("code") != "Ok" or not data.get("routes"):
                    logger.warning(f"[ROUTES] OSRM returned code: {data.get('code')}")
                    raise RuntimeError("No driving routes found between the specified locations.")

                raw_candidates = [r for r in data["routes"] if _is_valid_route(r)]
                if not raw_candidates:
                    raise RuntimeError("Routing service returned malformed route data.")

                # Filter duplicates based on geometry similarity & meaningful variation
                distinct_routes = deduplicate_routes(raw_candidates, settings.ROUTE_SIMILARITY_THRESHOLD)
                distinct_routes = distinct_routes[:settings.MAX_ROUTE_ALTERNATIVES]

                logger.info(f"[ROUTES] {len(distinct_routes)} distinct route alternatives retained from {len(raw_candidates)} candidates")

                parsed_routes = []
                for idx, r in enumerate(distinct_routes, start=1):
                    route_id = f"route_{idx}"
                    legs = r.get("legs", [])
                    summary_name = ""
                    if legs and isinstance(legs, list) and legs[0].get("summary"):
                        summary_name = legs[0]["summary"]

                    route_title = f"Route {idx}" + (f" (via {summary_name})" if summary_name else "")

                    dist_m = float(r.get("distance", 0.0))
                    dur_s = float(r.get("duration", 0.0))

                    parsed_routes.append({
                        "id": idx,
                        "route_id": route_id,
                        "name": route_title,
                        "distance_m": dist_m,
                        "duration_s": dur_s,
                        "distance_km": round(dist_m / 1000.0, 2),
                        "duration_min": round(dur_s / 60.0, 1),
                        "distance_meters": dist_m,       # Backward compatibility
                        "duration_seconds": dur_s,      # Backward compatibility
                        "geometry": r.get("geometry", {}),
                    })

                router_cache.set(cache_key, parsed_routes)
                return parsed_routes

        except httpx.TimeoutException as exc:
            logger.warning(f"[ROUTES] OSRM request timeout on attempt {attempt}/{max_retries}")
            last_error = exc
        except httpx.HTTPStatusError as exc:
            logger.warning(f"[ROUTES] OSRM HTTP error on attempt {attempt}/{max_retries}: {str(exc)}")
            last_error = exc
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning(f"[ROUTES] Unexpected OSRM error on attempt {attempt}/{max_retries}: {str(exc)}")
            last_error = exc

    logger.error(f"[ROUTES] All OSRM attempts failed: {str(last_error)}")
    if isinstance(last_error, httpx.TimeoutException):
        raise RuntimeError("Routing service timed out. Please try again.")
    raise RuntimeError("Failed to compute driving routes.")
