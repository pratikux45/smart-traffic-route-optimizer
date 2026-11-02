"""
Geographic math, spatial projection, distance, and route similarity utilities.
"""

import math
from typing import List, Tuple

EARTH_RADIUS_METERS = 6371000.0  # Earth's mean radius in meters


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth in meters.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return EARTH_RADIUS_METERS * c


def point_to_segment_projection(plat: float, plon: float,
                                lat1: float, lon1: float,
                                lat2: float, lon2: float) -> Tuple[float, float]:
    """
    Project point P(plat, plon) onto line segment A(lat1, lon1) -> B(lat2, lon2).
    Returns (distance_meters, t_projection_factor) where t is clamped to [0.0, 1.0].
    """
    if math.isclose(lat1, lat2, abs_tol=1e-7) and math.isclose(lon1, lon2, abs_tol=1e-7):
        return haversine_distance(plat, plon, lat1, lon1), 0.0

    # Local planar equirectangular approximation around segment
    cos_lat = math.cos(math.radians((lat1 + lat2) / 2.0))
    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 111320.0 * cos_lat

    px = (plon - lon1) * meters_per_deg_lon
    py = (plat - lat1) * meters_per_deg_lat

    bx = (lon2 - lon1) * meters_per_deg_lon
    by = (lat2 - lat1) * meters_per_deg_lat

    segment_len_sq = bx * bx + by * by
    if segment_len_sq == 0:
        return math.hypot(px, py), 0.0

    t = (px * bx + py * by) / segment_len_sq
    t_clamped = max(0.0, min(1.0, t))

    cx = t_clamped * bx
    cy = t_clamped * by

    dist = math.hypot(px - cx, py - cy)
    return dist, t_clamped


def point_to_segment_distance(plat: float, plon: float,
                               lat1: float, lon1: float,
                               lat2: float, lon2: float) -> float:
    """
    Calculate minimum distance in meters from point P(plat, plon)
    to line segment A(lat1, lon1) -> B(lat2, lon2).
    """
    dist, _ = point_to_segment_projection(plat, plon, lat1, lon1, lat2, lon2)
    return dist


def min_distance_to_polyline(plat: float, plon: float,
                             coords: List[List[float]]) -> float:
    """
    Calculate minimum distance in meters from point P(plat, plon)
    to a polyline given as a list of [lon, lat] coordinates (GeoJSON standard).
    """
    if not coords:
        return float('inf')

    if len(coords) == 1:
        return haversine_distance(plat, plon, coords[0][1], coords[0][0])

    min_dist = float('inf')
    for i in range(len(coords) - 1):
        lon1, lat1 = coords[i][0], coords[i][1]
        lon2, lat2 = coords[i + 1][0], coords[i + 1][1]

        # Quick spatial bounding check
        seg_min_lat = min(lat1, lat2) - 0.005
        seg_max_lat = max(lat1, lat2) + 0.005
        seg_min_lon = min(lon1, lon2) - 0.005
        seg_max_lon = max(lon1, lon2) + 0.005

        if not (seg_min_lat <= plat <= seg_max_lat and seg_min_lon <= plon <= seg_max_lon):
            continue

        dist = point_to_segment_distance(plat, plon, lat1, lon1, lat2, lon2)
        if dist < min_dist:
            min_dist = dist
            if min_dist == 0:
                break

    return min_dist


def calculate_distance_along_route(plat: float, plon: float,
                                   coords: List[List[float]]) -> float:
    """
    Calculate the cumulative driving distance in meters from the start of the route
    to the projected point of P(plat, plon) on the polyline.
    Coordinates are in GeoJSON [lon, lat] format.
    """
    if not coords or len(coords) < 2:
        return 0.0

    best_dist = float('inf')
    best_seg_idx = 0
    best_t = 0.0

    # Find the closest segment on the polyline
    for i in range(len(coords) - 1):
        lon1, lat1 = coords[i][0], coords[i][1]
        lon2, lat2 = coords[i + 1][0], coords[i + 1][1]

        dist, t = point_to_segment_projection(plat, plon, lat1, lon1, lat2, lon2)
        if dist < best_dist:
            best_dist = dist
            best_seg_idx = i
            best_t = t

    # Sum distances of preceding segments
    cumulative_distance = 0.0
    for i in range(best_seg_idx):
        lon1, lat1 = coords[i][0], coords[i][1]
        lon2, lat2 = coords[i + 1][0], coords[i + 1][1]
        cumulative_distance += haversine_distance(lat1, lon1, lat2, lon2)

    # Add partial distance of the matching segment
    s_lon1, s_lat1 = coords[best_seg_idx][0], coords[best_seg_idx][1]
    s_lon2, s_lat2 = coords[best_seg_idx + 1][0], coords[best_seg_idx + 1][1]
    seg_length = haversine_distance(s_lat1, s_lon1, s_lat2, s_lon2)
    cumulative_distance += (best_t * seg_length)

    return round(cumulative_distance, 1)


def sample_route_coordinates(coords: List[List[float]], num_samples: int = 50) -> List[Tuple[float, float]]:
    """
    Interpolate evenly spaced (lat, lon) sample coordinates along a polyline.
    Handles sparse vertices (e.g. 2 endpoints) and dense GPS tracks accurately.
    Coords are in GeoJSON [lon, lat] format; returns list of (lat, lon) tuples.
    """
    if not coords:
        return []
    if len(coords) == 1:
        return [(coords[0][1], coords[0][0])]
    if num_samples <= 2:
        return [(coords[0][1], coords[0][0]), (coords[-1][1], coords[-1][0])]

    # Compute cumulative distance for each segment
    seg_lengths: List[float] = []
    total_len = 0.0
    for i in range(len(coords) - 1):
        lon1, lat1 = coords[i][0], coords[i][1]
        lon2, lat2 = coords[i + 1][0], coords[i + 1][1]
        length = haversine_distance(lat1, lon1, lat2, lon2)
        seg_lengths.append(length)
        total_len += length

    if total_len <= 0.0:
        return [(coords[0][1], coords[0][0])] * num_samples

    step = total_len / (num_samples - 1)
    samples: List[Tuple[float, float]] = [(coords[0][1], coords[0][0])]

    curr_seg_idx = 0
    curr_seg_cum_start = 0.0

    for sample_i in range(1, num_samples - 1):
        target_dist = sample_i * step

        while (
            curr_seg_idx < len(seg_lengths) - 1
            and (curr_seg_cum_start + seg_lengths[curr_seg_idx]) < target_dist
        ):
            curr_seg_cum_start += seg_lengths[curr_seg_idx]
            curr_seg_idx += 1

        seg_len = seg_lengths[curr_seg_idx]
        if seg_len > 0:
            t = (target_dist - curr_seg_cum_start) / seg_len
            t = max(0.0, min(1.0, t))
        else:
            t = 0.0

        lon1, lat1 = coords[curr_seg_idx][0], coords[curr_seg_idx][1]
        lon2, lat2 = coords[curr_seg_idx + 1][0], coords[curr_seg_idx + 1][1]
        interp_lat = lat1 + t * (lat2 - lat1)
        interp_lon = lon1 + t * (lon2 - lon1)
        samples.append((interp_lat, interp_lon))

    samples.append((coords[-1][1], coords[-1][0]))
    return samples


def calculate_route_similarity(coords_a: List[List[float]],
                               coords_b: List[List[float]],
                               match_threshold_m: float = 35.0,
                               sample_limit: int = 50) -> float:
    """
    Calculate the geometric similarity ratio between two route polylines [0.0, 1.0].
    Evenly samples coordinates along the true cumulative distance of both routes
    and measures the mutual proximity to the other's polyline.
    Returns the symmetric average overlap [0.0, 1.0].
    """
    if not coords_a or not coords_b:
        return 0.0

    samples_a = sample_route_coordinates(coords_a, num_samples=sample_limit)
    samples_b = sample_route_coordinates(coords_b, num_samples=sample_limit)

    if not samples_a or not samples_b:
        return 0.0

    # Ratio of Route A samples overlapping Route B
    matched_a = sum(1 for lat, lon in samples_a if min_distance_to_polyline(lat, lon, coords_b) <= match_threshold_m)
    overlap_a = matched_a / max(1, len(samples_a))

    # Ratio of Route B samples overlapping Route A
    matched_b = sum(1 for lat, lon in samples_b if min_distance_to_polyline(lat, lon, coords_a) <= match_threshold_m)
    overlap_b = matched_b / max(1, len(samples_b))

    # Symmetric similarity: true mutual overlap
    # Two routes are duplicates only if BOTH directions show high overlap.
    return round((overlap_a + overlap_b) / 2.0, 3)


def calculate_bounding_box(coords_list: List[List[List[float]]],
                           margin_degrees: float = 0.01) -> Tuple[float, float, float, float]:
    """
    Calculate bounding box (min_lat, min_lon, max_lat, max_lon)
    covering all points across a list of route geometries (each is [[lon, lat], ...]).
    Includes a safety margin (default ~1km).
    """
    all_lats = []
    all_lons = []

    for route in coords_list:
        for point in route:
            all_lons.append(point[0])
            all_lats.append(point[1])

    if not all_lats or not all_lons:
        return (0.0, 0.0, 0.0, 0.0)

    min_lat = max(-90.0, min(all_lats) - margin_degrees)
    max_lat = min(90.0, max(all_lats) + margin_degrees)
    min_lon = max(-180.0, min(all_lons) - margin_degrees)
    max_lon = min(180.0, max(all_lons) + margin_degrees)

    return (min_lat, min_lon, max_lat, max_lon)
