"""Build a census-style village CSV extract from OpenStreetMap for any district.

Usage:
    python -m scripts.build_osm_extract --district Madurai

Queries Overpass for the district's administrative area (admin_level=5) and
collects named populated places (city|town|village|hamlet) inside it, writing
data/census_<slug>.csv in the census CSV format the ingest pipeline reads.
The taluk column is left blank: merge_osm_places() assigns every place to a
block by nearest centroid (with curated overrides) at ingest time, so this
extract is purely a coordinate / Tamil-name source, not an authority on blocks.

WARNING: The extract is NOT authoritative. OSM covers only a fraction of the
official villages in a district, and boundary areas can lag the census block
map. The ingestion reconciliation gate counts only census-file villages, so
gaps here never cause a silent drop — they surface as missing coordinates.

Use the Overpass endpoint mirror if the default is unreachable:
    python -m scripts.build_osm_extract --district Madurai \
        --endpoint https://overpass-api.de/api/interpreter
"""
from __future__ import annotations

import argparse
import csv
import json

import httpx
from slugify import slugify

from app.config import settings

# OSM admin-area names that differ from the census/UI district spelling.
AREA_NAME_ALIASES: dict[str, str] = {
    "Villupuram": "Viluppuram",
    "Tiruvallur": "Thiruvallur",
    "The Nilgiris": "Nilgiris",
    "Tiruvarur": "Thiruvarur",
    "Thoothukkudi": "Thoothukudi",
}


def fetch_places(district: str, endpoint: str) -> list[dict]:
    query = f"""
    [out:json][timeout:{int(settings.overpass_timeout_seconds)}];
    area["name"="{district}"]["boundary"="administrative"]["admin_level"="5"]->.a;
    (
      node["place"~"^(city|town|village|hamlet)$"]["name"](area.a);
    );
    out body;
    """
    resp = httpx.get(
        endpoint,
        params={"data": query},
        headers={"User-Agent": settings.overpass_user_agent},
        timeout=settings.overpass_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json().get("elements", [])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--district", default="Villupuram", help="District name (e.g. Madurai)")
    parser.add_argument(
        "--area-name",
        default=None,
        help="OSM admin-area name if it differs from --district "
        "(e.g. Viluppuram for Villupuram)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output CSV path (default: data/census_<slug>.csv)",
    )
    parser.add_argument(
        "--endpoint", default=settings.overpass_api_url, help="Overpass API endpoint"
    )
    args = parser.parse_args()

    district = args.district or "Villupuram"
    area_name = args.area_name or AREA_NAME_ALIASES.get(district, district)
    elements = fetch_places(area_name, args.endpoint)
    out = args.out or f"data/census_{slugify(args.district, lowercase=True)}.csv"

    rows: dict[str, list[str]] = {}
    for el in elements:
        tags = el.get("tags", {})
        name = (tags.get("name") or "").strip()
        lat, lng = el.get("lat"), el.get("lon")
        if not name or lat is None or lng is None:
            continue
        rows.setdefault(name.lower(), [
            name,
            "",
            args.district,
            "",
            f"{lat:.5f}",
            f"{lng:.5f}",
            tags.get("name:ta") or "",
            tags.get("place") or "village",
        ])

    with open(out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["village", "taluk", "district", "census_code", "lat", "lng", "name_ta", "place_type"]
        )
        for row in sorted(rows.values(), key=lambda r: r[0]):
            writer.writerow(row)

    by_place: dict[str, int] = {}
    for el in elements:
        t = el.get("tags", {}).get("place")
        if t:
            by_place[t] = by_place.get(t, 0) + 1
    print(f"Wrote {len(rows)} places for {args.district} to {out}")
    for kind, count in sorted(by_place.items()):
        print(f"  {kind}: {count}")


if __name__ == "__main__":
    main()
