"""Route building: OSRM driving route + automatic village-stop snapping.

Drivers only ever pick a start and end village. The app computes the road
polyline (OSRM), attaches nearby villages as stops, and de-duplicates so
the same village pair reuses an existing route.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Route, RouteStop, Village
from app.services.geo import Point, point_to_polyline_distance, polyline_length

logger = logging.getLogger(__name__)

GEOJSON_POLYLINE: dict | None = None

# Injectable for tests (avoids network dependency in unit tests).
_osrm_http_client: httpx.AsyncClient | None = None
_osrm_fallback_mode = False


def configure_osrm(client: httpx.AsyncClient | None = None, fallback: bool = False) -> None:
    global _osrm_http_client, _osrm_fallback_mode
    _osrm_http_client = client
    _osrm_fallback_mode = fallback


def _fallback_polyline(start: Point, end: Point) -> list[Point]:
    """Deterministic straight-ish polyline between two points (no network).

    Only used in dev/tests when OSRM is unreachable. Passing through the real
    start/end keeps GPS fixes near the villages on-route (so they are not
    flagged anomalous), which also keeps anomaly/history logic testable.
    """
    lat1, lng1 = start
    lat2, lng2 = end
    dlng = lng2 - lng1
    # Gentle sideways bulge at the midpoint so routes are not perfectly straight.
    mid = (
        (lat1 + lat2) / 2.0 + dlng * 0.01,
        (lng1 + lng2) / 2.0 - (lat2 - lat1) * 0.01,
    )
    return [start, mid, end]


async def fetch_driving_polyline(
    start: Point, end: Point, client: httpx.AsyncClient | None = None
) -> list[Point]:
    """Get a [lat, lng] polyline between two points from the OSRM public API."""
    if _osrm_fallback_mode:
        return _fallback_polyline(start, end)
    http = client or _osrm_http_client
    if http is None:
        http = httpx.AsyncClient(timeout=settings.osrm_timeout_seconds)
    url = (
        f"{settings.osrm_base_url}/route/v1/driving/"
        f"{end[1]},{end[0]};{start[1]},{start[0]}"
        "?overview=full&geometries=geojson"
    )
    resp = await http.get(url)
    resp.raise_for_status()
    data = resp.json()
    routes = data.get("routes") or []
    if not routes:
        raise ValueError("OSRM returned no route")
    coords = routes[0].get("geometry", {}).get("coordinates", [])
    if len(coords) < 2:
        raise ValueError("OSRM returned degenerate route")
    # GeoJSON coordinates are (lng, lat).
    return [(lat, lng) for lng, lat in coords]


def route_fingerprint(start: Point, end: Point) -> str:
    """Deterministic key used to de-duplicate routes for the same pair."""
    key = f"{start[0]:.5f},{start[1]:.5f}|{end[0]:.5f},{end[1]:.5f}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


@dataclass
class RouteBuildResult:
    route: Route
    stops: list[RouteStop]
    created: bool


async def build_route(
    db: AsyncSession,
    district_id: int,
    from_village: Village,
    to_village: Village,
) -> RouteBuildResult:
    """Build (or reuse) a route between two villages within a district."""
    if not from_village.has_coords or not to_village.has_coords:
        from app.api.errors import BadRequestError

        raise BadRequestError(
            "Selected villages do not have coordinates yet; route cannot be built."
        )
    if from_village.id == to_village.id:
        from app.api.errors import BadRequestError

        raise BadRequestError("Start and destination must differ.")

    # has_coords was checked above, so lat/lng are present here.
    assert from_village.lat is not None and from_village.lng is not None
    assert to_village.lat is not None and to_village.lng is not None
    start: Point = (from_village.lat, from_village.lng)
    end: Point = (to_village.lat, to_village.lng)
    fp = route_fingerprint(start, end)

    # 1) Reuse an existing route for the same village pair within the district.
    existing = await db.scalar(
        select(Route).where(
            and_(
                Route.district_id == district_id,
                Route.from_village_id == from_village.id,
                Route.to_village_id == to_village.id,
                Route.source == "driver_built",
            )
        )
    )
    if existing is not None:
        stops = list(
            (
                await db.execute(
                    select(RouteStop).where(RouteStop.route_id == existing.id)
                )
            )
            .scalars()
            .all()
        )
        return RouteBuildResult(existing, stops, created=False)

    # 2) Fetch the driving polyline.
    try:
        polyline = await fetch_driving_polyline(start, end)
    except Exception as exc:  # noqa: BLE001 - surface a friendly error
        logger.warning("OSRM route fetch failed: %s", exc)
        from app.api.errors import BadRequestError

        raise BadRequestError(
            "Could not compute a road route between these villages. "
            "Please try again or pick nearby villages."
        ) from exc

    distance_m = polyline_length(polyline)
    route = Route(
        district_id=district_id,
        from_village_id=from_village.id,
        to_village_id=to_village.id,
        polyline=polyline,
        distance_m=distance_m,
        duration_estimate_min=distance_m / 1000.0 / 35.0 * 60.0,
        source="driver_built",
        status="unverified",
    )
    db.add(route)
    await db.flush()

    # 3) Snap nearby villages as stops, ordered by progress along the route.
    villages = (
        await db.execute(
            select(Village).where(
                and_(
                    Village.district_id == district_id,
                    Village.has_coords.is_(True),
                )
            )
        )
    ).scalars().all()

    snapped: list[tuple[float, Village]] = []
    from app.services.geo import project_point_on_polyline

    for village in villages:
        if village.id in (from_village.id, to_village.id):
            continue
        if village.lat is None or village.lng is None:
            continue
        point: Point = (village.lat, village.lng)
        dist = point_to_polyline_distance(point, polyline)
        if dist <= settings.route_snap_threshold_m:
            progress, _, _, _ = project_point_on_polyline(point, polyline)
            snapped.append((progress, village))

    stops: list[RouteStop] = []
    seq = 0
    ordered = [
        (0.0, from_village),
        *sorted(snapped, key=lambda item: item[0]),
        (1.0, to_village),
    ]
    for progress, village in ordered:
        stop = RouteStop(
            route_id=route.id,
            village_id=village.id,
            seq=seq,
            progress=progress,
        )
        db.add(stop)
        stops.append(stop)
        seq += 1

    await db.commit()
    await db.refresh(route)
    return RouteBuildResult(route, stops, created=True)
