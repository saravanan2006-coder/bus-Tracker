"""Pure-Python geospatial helpers (haversine + polyline projection).

These run everywhere (SQLite tests, Postgres prod) and are cheap enough for
the ~2k req/s ingest peak. PostGIS remains available for SQL-heavy scans.
"""
from __future__ import annotations

import math
from typing import TypeAlias

Point: TypeAlias = tuple[float, float]  # (lat, lng)
Polyline: TypeAlias = list[Point]

EARTH_RADIUS_M = 6_371_008.8


def haversine(a: Point, b: Point) -> float:
    """Great-circle distance in metres between two lat/lng points."""
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def _local_xy(point: Point, ref: Point) -> tuple[float, float]:
    """Equirectangular projection of `point` relative to `ref` in metres."""
    lat_r = math.radians(ref[0])
    x = math.radians(point[1] - ref[1]) * math.cos(lat_r) * EARTH_RADIUS_M
    y = math.radians(point[0] - ref[0]) * EARTH_RADIUS_M
    return x, y


def point_segment_distance(point: Point, seg_a: Point, seg_b: Point) -> float:
    """Shortest distance in metres from `point` to the segment a-b."""
    ref = (point[0], point[1])
    px, py = _local_xy(point, ref)
    ax, ay = _local_xy(seg_a, ref)
    bx, by = _local_xy(seg_b, ref)
    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def point_to_polyline_distance(point: Point, polyline: Polyline) -> float:
    if len(polyline) < 2:
        return haversine(point, polyline[0]) if polyline else float("inf")
    return min(
        point_segment_distance(point, polyline[i], polyline[i + 1])
        for i in range(len(polyline) - 1)
    )


def polyline_length(polyline: Polyline) -> float:
    if len(polyline) < 2:
        return 0.0
    return sum(
        haversine(polyline[i], polyline[i + 1]) for i in range(len(polyline) - 1)
    )


def project_point_on_polyline(
    point: Point, polyline: Polyline
) -> tuple[float, float, float, Point]:
    """Project a point onto a polyline.

    Returns (progress, distance_along_m, distance_to_line_m, snapped_point)
    where progress is 0.0 at the start and 1.0 at the end.
    """
    if len(polyline) == 0:
        return 0.0, 0.0, float("inf"), point
    if len(polyline) == 1:
        d = haversine(point, polyline[0])
        return 0.0, 0.0, d, polyline[0]

    ref = (point[0], point[1])
    px, py = _local_xy(point, ref)

    # Precompute segment lengths in projected space (proportional to metres).
    seg_lengths: list[float] = []
    cumulative = 0.0
    for i in range(len(polyline) - 1):
        ax, ay = _local_xy(polyline[i], ref)
        bx, by = _local_xy(polyline[i + 1], ref)
        length = math.hypot(bx - ax, by - ay)
        seg_lengths.append(length)
        cumulative += length
    if cumulative == 0.0:
        return 0.0, 0.0, point_to_polyline_distance(point, polyline), polyline[0]

    best_i = -1
    best_t = 0.0
    best_dist = float("inf")
    for i, (length) in enumerate(seg_lengths):
        ax, ay = _local_xy(polyline[i], ref)
        bx, by = _local_xy(polyline[i + 1], ref)
        dx, dy = bx - ax, by - ay
        if length == 0:
            dist = math.hypot(px - ax, py - ay)
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (length * length)))
            dist = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
        if dist < best_dist:
            best_dist, best_i, best_t = dist, i, t

    distance_along = sum(seg_lengths[:best_i]) + best_t * seg_lengths[best_i]
    progress = distance_along / cumulative
    snapped = (
        polyline[best_i][0] + best_t * (polyline[best_i + 1][0] - polyline[best_i][0]),
        polyline[best_i][1] + best_t * (polyline[best_i + 1][1] - polyline[best_i][1]),
    )
    return progress, distance_along, best_dist, snapped


def progress_to_distance(progress: float, total_m: float) -> float:
    """Distance in metres from the route start at a given progress."""
    return max(0.0, min(1.0, progress)) * total_m


def point_at_fraction(polyline: Polyline, fraction: float) -> Point:
    """Point on the polyline at a given fraction of its length (0.0 -> 1.0).

    Walks along the great-circle distances between consecutive points, so the
    interpolation is proportional to true metres travelled, not index order.
    """
    fraction = max(0.0, min(1.0, fraction))
    if not polyline:
        raise ValueError("empty polyline")
    if len(polyline) == 1:
        return polyline[0]
    if fraction == 0.0:
        return polyline[0]
    if fraction == 1.0:
        return polyline[-1]

    cumulative = [0.0]
    for i in range(len(polyline) - 1):
        cumulative.append(cumulative[-1] + haversine(polyline[i], polyline[i + 1]))
    total = cumulative[-1]
    if total == 0.0:
        return polyline[0]
    target = fraction * total
    for i in range(len(polyline) - 1):
        if cumulative[i + 1] >= target:
            seg_len = cumulative[i + 1] - cumulative[i]
            t = 0.0 if seg_len <= 0 else (target - cumulative[i]) / seg_len
            return (
                polyline[i][0] + (polyline[i + 1][0] - polyline[i][0]) * t,
                polyline[i][1] + (polyline[i + 1][1] - polyline[i][1]) * t,
            )
    return polyline[-1]


def speed_between(a: Point, b: Point, seconds: float) -> float:
    """Speed in km/h between two points over `seconds`."""
    if seconds <= 0:
        return 0.0
    return (haversine(a, b) / 1000.0) / (seconds / 3600.0)
