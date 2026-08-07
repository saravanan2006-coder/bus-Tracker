"""Unit tests for the pure geospatial helpers."""
from __future__ import annotations

import pytest

from app.services.geo import (
    haversine,
    point_segment_distance,
    point_to_polyline_distance,
    polyline_length,
    project_point_on_polyline,
    speed_between,
)

CHENNAI = (13.0827, 80.2707)
MADURAI = (9.9252, 78.1198)


def test_haversine_chennai_madurai():
    distance = haversine(CHENNAI, MADURAI)
    assert 400_000 < distance < 470_000


def test_haversine_same_point_is_zero():
    assert haversine(CHENNAI, CHENNAI) == 0.0


def test_point_on_segment_zero_distance():
    a = (10.0, 78.0)
    b = (10.0, 78.05)
    point = (10.0, 78.025)
    assert point_segment_distance(point, a, b) < 1.0


def test_point_off_segment_distance():
    a = (10.0, 78.0)
    b = (10.0, 78.05)
    point = (10.0, 78.025,)
    # Same as above; instead use a clearly offset point.
    offset = (10.01, 78.025)
    assert point_segment_distance(offset, a, b) > 900  # ~1.1 km


def test_polyline_length_equals_haversine_for_two_points():
    line = [CHENNAI, MADURAI]
    assert abs(polyline_length(line) - haversine(CHENNAI, MADURAI)) < 1e-6


def test_project_start_and_end():
    line = [(10.0, 78.0), (10.0, 78.05), (10.0, 78.10)]
    progress_start, dist_start, _, _ = project_point_on_polyline(line[0], line)
    progress_end, dist_end, _, _ = project_point_on_polyline(line[-1], line)
    assert progress_start == pytest.approx(0.0)
    assert progress_end == pytest.approx(1.0)
    assert dist_end > dist_start


def test_project_midpoint_half_progress():
    line = [(10.0, 78.0), (10.0, 78.10)]
    mid = (10.0, 78.05)
    progress, dist, off, _ = project_point_on_polyline(mid, line)
    assert progress == pytest.approx(0.5, abs=0.01)
    assert off < 1.0


def test_point_to_polyline_distance():
    line = [(10.0, 78.0), (10.0, 78.10)]
    offset = (10.01, 78.05)
    assert point_to_polyline_distance(offset, line) > 1000


def test_speed_between():
    # ~55.5 km in 1 hour from Chennai toward the south should be ~55 km/h.
    speed = speed_between(CHENNAI, (12.58, 80.27), 3600)
    assert 50 < speed < 60
