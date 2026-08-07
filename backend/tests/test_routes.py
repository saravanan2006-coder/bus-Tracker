"""Route building tests: OSRM fallback polyline, stops, and de-duplication."""
from __future__ import annotations

from sqlalchemy import select

from app.api.errors import BadRequestError
from app.models import Route, RouteStop, Village
from app.services.route_service import build_route, route_fingerprint


async def test_route_build_with_fallback(db, fixtures):
    route = await fixtures["make_route"]("Villupuram", "Tindivanam")
    assert route.id is not None
    assert route.distance_m and route.distance_m > 0
    assert len(route.polyline) >= 2

    stops = (
        (await db.execute(select(RouteStop).where(RouteStop.route_id == route.id)))
        .scalars()
        .all()
    )
    from_v = await db.get(Village, route.from_village_id)
    to_v = await db.get(Village, route.to_village_id)
    stop_village_ids = {s.village_id for s in stops}
    assert from_v.id in stop_village_ids
    assert to_v.id in stop_village_ids
    # Ordered by seq with progress monotonic.
    seqs = sorted(stops, key=lambda s: s.seq)
    for a, b in zip(seqs, seqs[1:]):
        assert b.progress >= a.progress


async def test_route_dedupes_same_pair(db, fixtures):
    first = await fixtures["make_route"]("Villupuram", "Tindivanam")
    fv = await db.get(Village, first.from_village_id)
    tv = await db.get(Village, first.to_village_id)
    result = await build_route(db, first.district_id, fv, tv)
    assert result.created is False
    assert result.route.id == first.id


def test_fingerprint_is_deterministic():
    a = route_fingerprint((11.93, 79.49), (12.23, 79.65))
    b = route_fingerprint((11.93, 79.49), (12.23, 79.65))
    assert a == b


async def test_route_requires_different_villages(db, fixtures):
    village = await db.get(Village, await fixtures["village_id"]("Villupuram", "Villupuram"))
    try:
        await build_route(db, village.district_id, village, village)
        assert False, "expected BadRequestError"
    except BadRequestError:
        pass
