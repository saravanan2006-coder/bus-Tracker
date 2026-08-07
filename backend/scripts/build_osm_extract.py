"""Build a census-style village CSV extract from OpenStreetMap.

Usage:
    python -m scripts.build_osm_extract --input /path/to/osm_elements.json \
        --out data/census_villupuram.csv

The input is the `elements` array from an Overpass `out body;` query for
places (`city|town|village|hamlet`) inside the Villupuram-region bounding
box. Each place is assigned to a taluk by nearest headquarters distance.

WARNING: This extract is NOT authoritative. OSM covers only a fraction of
the ~929 revenue villages in Villupuram district, and nearest-HQ assignment
can mislabel border places. The ingestion reconciliation gate is expected to
block publishing on this extract — that is the intended guarantee. Real
Census 2011 / TNRD village lists must be supplied for production.
"""
from __future__ import annotations

import argparse
import csv
import json

from app.services.geo import haversine

# Taluk headquarters (current 9 taluks of Villupuram district).
# Sources: Wikipedia / official district pages. Post-2019 taluk map.
TALUK_HQS: dict[str, tuple[float, float]] = {
    "Villupuram": (11.9398, 79.4947),
    "Vanur": (12.0025, 79.6638),
    "Tindivanam": (12.2343, 79.6554),
    "Gingee": (12.2523, 79.4173),
    "Vikravandi": (12.0345, 79.5440),
    "Marakkanam": (12.2062, 79.9488),
    "Kandachipuram": (12.03944, 79.30028),
    "Melmalaiyanur": (12.3061, 79.3094),
    "Thiruvennainallur": (11.87917, 79.37889),
}

DISTRICT = "Villupuram"

# Towns from the curated fixture that OSM may not tag as places.
FIXTURE_TOWNS: list[tuple[str, str, float, float]] = [
    ("Villupuram", "விழுப்புரம்", 11.9398, 79.4947),
    ("Tindivanam", "திண்டிவனம்", 12.2343, 79.6554),
    ("Gingee", "செஞ்சி", 12.2523, 79.4173),
    ("Vanur", "வானூர்", 12.0025, 79.6638),
    ("Marakkanam", "மரக்காணம்", 12.2062, 79.9488),
    ("Vikravandi", "விக்கிரவாண்டி", 12.0345, 79.5440),
    ("Koliyanur", "கொளியனூர்", 11.9950, 79.6146),
    ("Mugaiyur", "முகையூர்", 11.9144, 79.2877),
    ("Ulundurpet", "உளுந்தூர்பேட்டை", 11.6907, 79.3140),
    ("Tirukoilur", "திருக்கோவிலூர்", 11.9583, 79.2033),
]


def nearest_taluk(lat: float, lng: float) -> tuple[str, float]:
    best = min(
        TALUK_HQS.items(),
        key=lambda item: haversine((lat, lng), item[1]),
    )
    return best[0], haversine((lat, lng), best[1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Overpass elements JSON")
    parser.add_argument(
        "--out", default="data/census_villupuram.csv", help="Output CSV path"
    )
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as fh:
        elements = json.load(fh)

    rows: dict[tuple[str, str], list[str]] = {}
    for el in elements:
        tags = el.get("tags", {})
        name = (tags.get("name") or "").strip()
        lat, lng = el.get("lat"), el.get("lon")
        if not name or lat is None or lng is None:
            continue
        if tags.get("place") == "city":
            continue
        taluk, _ = nearest_taluk(lat, lng)
        key = (taluk, name.lower())
        rows[key] = [
            name,
            taluk,
            DISTRICT,
            "",
            f"{lat:.5f}",
            f"{lng:.5f}",
            tags.get("name:ta") or "",
        ]

    for name, name_ta, lat, lng in FIXTURE_TOWNS:
        taluk, _ = nearest_taluk(lat, lng)
        key = (taluk, name.lower())
        rows.setdefault(key, [name, taluk, DISTRICT, "", f"{lat:.5f}", f"{lng:.5f}", name_ta])

    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["village", "taluk", "district", "census_code", "lat", "lng", "name_ta"]
        )
        for row in sorted(rows.values(), key=lambda r: (r[1], r[0])):
            writer.writerow(row)

    from collections import Counter

    by_taluk = Counter(r[1] for r in rows.values())
    print(f"Wrote {len(rows)} rows to {args.out}")
    for taluk in TALUK_HQS:
        print(f"  {taluk}: {by_taluk.get(taluk, 0)}")


if __name__ == "__main__":
    main()
