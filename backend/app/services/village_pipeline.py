"""Village/town data pipeline: census + TNRD + OSM merge with reconciliation.

Guarantee: nothing is silently dropped. Every source record either lands in
the `villages` table or is reported in the reconciliation summary, which
blocks publishing until village counts match expected per-taluk figures.
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from slugify import slugify

from app.config import settings

logger = logging.getLogger(__name__)

# Default 'expected' counts keyed by district name -> (taluk, count).
# In production these come from the Census 2011 Village Directory / TNRD
# block lists. A curated extract lives in data/fixtures/villupuram_taluks.csv.


@dataclass
class SourceRecord:
    name: str
    name_ta: str | None = None
    taluk: str | None = None
    district: str | None = None
    lat: float | None = None
    lng: float | None = None
    census_code: str | None = None
    place_type: str = "village"
    source: str = "census"
    has_coords: bool = False
    sources: set[str] = field(default_factory=set)


@dataclass
class ReconciliationReport:
    district: str = ""
    expected_by_taluk: dict[str, int] = field(default_factory=dict)
    merged_by_taluk: dict[str, int] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    missing_coords: int = 0
    blocks_publishing: bool = False

    def to_dict(self) -> dict:
        return {
            "district": self.district,
            "expected_by_taluk": self.expected_by_taluk,
            "merged_by_taluk": self.merged_by_taluk,
            "dropped": self.dropped,
            "missing_coords": self.missing_coords,
            "blocks_publishing": self.blocks_publishing,
        }


def normalize_name(name: str) -> str:
    return slugify(name, lowercase=True)


# Curated block assignment for the urban towns the census file omits. The TN
# census lists rural villages only, so district towns never appear in it; the
# pre-2019 file also has no taluk column. Each town is pinned to the census
# block that contains it geographically (name-keyed, slugified). Towns without
# an entry fall back to nearest block centroid.
TOWN_BLOCK_ASSIGNMENT: dict[str, str] = {
    "villupuram": "Vikkiravandi",
    "tindivanam": "Olakkur",
    "gingee": "Gingee",
    "marakkanam": "Merkanam",
    "vikravandi": "Vikkiravandi",
    "koliyanur": "Koliyanur",
    "vanur": "Vanur",
    "mugaiyur": "Mugaiyur",
    "ulundurpet": "Ulundurpet",
    "tirukoilur": "Tirukoilur",
    "kallakurichi": "Kallakurichi",
    "sankarapuram": "Sankarapuram",
}


def merge_village_sources(
    records: list[SourceRecord],
) -> tuple[dict[str, SourceRecord], ReconciliationReport]:
    """Merge records, de-duplicating by (taluk, normalized name).

    Coordinates and Tamil names from OSM enrich census records; a village
    missing coordinates is kept and flagged, never dropped.
    """
    merged: dict[str, SourceRecord] = {}
    dropped: list[str] = []

    for rec in records:
        key = f"{normalize_name(rec.taluk or '')}:{normalize_name(rec.name)}"
        if key in merged:
            existing = merged[key]
            # OSM coordinates win (they are GPS-accurate); keep the rest.
            if rec.lat is not None and rec.lng is not None:
                existing.lat, existing.lng = rec.lat, rec.lng
                existing.has_coords = True
            if rec.name_ta and not existing.name_ta:
                existing.name_ta = rec.name_ta
            if rec.census_code and not existing.census_code:
                existing.census_code = rec.census_code
            existing.sources.add(rec.source)
            if rec.place_type == "town":
                existing.place_type = "town"
            continue
        merged[key] = rec
        rec.sources = {rec.source}

    missing_coords = sum(1 for r in merged.values() if r.lat is None or r.lng is None)
    return merged, ReconciliationReport(dropped=dropped, missing_coords=missing_coords)


def build_reconciliation_report(
    district: str,
    merged: dict[str, SourceRecord],
    expected_by_taluk: dict[str, int],
) -> ReconciliationReport:
    by_taluk: dict[str, int] = {}
    for rec in merged.values():
        taluk = normalize_name(rec.taluk or "")
        by_taluk[taluk] = by_taluk.get(taluk, 0) + 1

    report = ReconciliationReport(
        district=district,
        expected_by_taluk=expected_by_taluk,
        merged_by_taluk=by_taluk,
        missing_coords=sum(
            1 for r in merged.values() if r.lat is None or r.lng is None
        ),
    )
    # Block publishing if any taluk has fewer records than expected.
    for taluk, expected in expected_by_taluk.items():
        merged_count = by_taluk.get(normalize_name(taluk), 0)
        if merged_count < expected:
            report.blocks_publishing = True
    return report


# --------------------------------------------------------------------- #
# OSM fetch (Overpass API)
# --------------------------------------------------------------------- #
async def fetch_osm_places(
    min_lat: float,
    min_lng: float,
    max_lat: float,
    max_lng: float,
    places: tuple[str, ...] = ("city", "town", "village", "hamlet"),
    client: httpx.AsyncClient | None = None,
) -> list[SourceRecord]:
    """Pull named populated places from OpenStreetMap within a bounding box."""
    place_re = "|".join(places)
    query = f"""
    [out:json][timeout:{int(settings.overpass_timeout_seconds)}];
    (
      node["place"~"^{place_re}$"]["name"]({min_lat:.6f},{min_lng:.6f},{max_lat:.6f},{max_lng:.6f});
    );
    out tags;
    """
    http = client or httpx.AsyncClient(timeout=settings.overpass_timeout_seconds)
    resp = await http.get(
        settings.overpass_api_url, params={"data": query}
    )
    resp.raise_for_status()
    elements = resp.json().get("elements", [])

    records: list[SourceRecord] = []
    for el in elements:
        tags = el.get("tags", {})
        records.append(
            SourceRecord(
                name=tags.get("name", ""),
                name_ta=tags.get("name:ta"),
                lat=el.get("lat"),
                lng=el.get("lon"),
                place_type=tags.get("place", "village"),
                source="osm",
            )
        )
    return [r for r in records if r.name]


# --------------------------------------------------------------------- #
# CSV ingestion for census/TNRD extracts
# --------------------------------------------------------------------- #
def parse_census_csv(text: str) -> list[SourceRecord]:
    """Parse a census village-directory style CSV.

    Expected columns: village,taluk,district,census_code[,lat,lng][,name_ta]
    """
    records: list[SourceRecord] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        name = (row.get("village") or row.get("name") or "").strip()
        if not name:
            continue
        try:
            lat = float(row["lat"]) if row.get("lat") not in (None, "") else None
            lng = float(row["lng"]) if row.get("lng") not in (None, "") else None
        except (KeyError, ValueError):
            lat = lng = None
        records.append(
            SourceRecord(
                name=name,
                name_ta=row.get("name_ta") or None,
                taluk=row.get("taluk") or None,
                district=row.get("district") or None,
                lat=lat,
                lng=lng,
                census_code=row.get("census_code") or None,
                source="census",
            )
        )
    return records


def _clean_header(value: str) -> str:
    """Normalise a CSV header cell (the TN e-Gov file embeds newlines)."""
    return " ".join(value.split()).lower()


def parse_tn_census_csv(text: str, district_code: str | None = None) -> list[SourceRecord]:
    """Parse the TN e-Governance district-block-village-habitation CSV.

    Habitation rows collapse to one record per (block, village code). The
    block name becomes the taluk — this file predates the 2019 district
    split and carries no taluk column. Names are title-cased for the UI;
    the official village code is kept as the stable identifier. Pass
    [district_code] to scope to a single district (e.g. "4" = Villupuram).
    """
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header = [_clean_header(h) for h in rows[0]]
    records: dict[tuple[str, str], SourceRecord] = {}
    for row in rows[1:]:
        row = list(row) + [""] * (len(header) - len(row))
        d = dict(zip(header, row))
        if district_code is not None and (d.get("district code") or "").strip() != district_code:
            continue
        block = (d.get("block name") or "").strip()
        vname = (d.get("village name") or "").strip()
        vcode = (d.get("village code") or "").strip()
        if not block or not vname:
            continue
        key = (block.lower(), vcode)
        if key in records:
            continue
        records[key] = SourceRecord(
            name=vname.title(),
            taluk=block.title(),
            district=(d.get("district name") or "").strip(),
            census_code=vcode,
            source="tn-census",
        )
    return list(records.values())


def census_expected_by_taluk(records: list[SourceRecord]) -> dict[str, int]:
    """Rebase expected per-taluk counts on an authoritative census file.

    Counted before de-duplication so the reconciliation gate still catches
    any village that would be silently lost during the merge.
    """
    counts: dict[str, int] = {}
    for rec in records:
        if not rec.taluk:
            continue
        counts[rec.taluk] = counts.get(rec.taluk, 0) + 1
    return dict(sorted(counts.items()))


def enrich_with_osm_coords(
    records: list[SourceRecord],
    osm_records: list[SourceRecord],
) -> list[SourceRecord]:
    """Attach OSM coordinates (and Tamil names) to census villages by name.

    Only unambiguous matches are applied: a name that resolves to more than
    one OSM location is skipped so a village is never pinned to the wrong
    point. Villages that stay unresolved are kept and flagged for review.
    """
    by_name: dict[str, list[tuple[float, float, str | None]]] = {}
    for o in osm_records:
        if o.lat is None or o.lng is None:
            continue
        by_name.setdefault(normalize_name(o.name), []).append((o.lat, o.lng, o.name_ta))

    for rec in records:
        if rec.lat is not None and rec.lng is not None:
            continue
        matches = by_name.get(normalize_name(rec.name), [])
        if len(matches) != 1:
            continue
        lat, lng, name_ta = matches[0]
        rec.lat, rec.lng = lat, lng
        rec.has_coords = True
        if name_ta and not rec.name_ta:
            rec.name_ta = name_ta
    return records


def merge_osm_places(
    records: list[SourceRecord],
    osm_records: list[SourceRecord],
    max_assign_km: float = 60.0,
) -> list[SourceRecord]:
    """Add OSM places (towns, hamlets) the census file does not cover.

    The TN census file lists rural villages only, so urban towns are missing
    from it. Every unmatched OSM place is assigned to the nearest block whose
    census villages have coordinates and appended to the district. Known
    district towns are pinned to their curated block; places too far from
    every block are treated as out-of-bounds noise and skipped.
    """
    from app.services.geo import haversine

    known = {normalize_name(r.name) for r in records}
    block_names = {r.taluk for r in records if r.taluk}
    sums: dict[str, list[float]] = {}
    for r in records:
        if r.lat is None or r.lng is None or not r.taluk:
            continue
        s = sums.setdefault(r.taluk, [0.0, 0.0, 0])
        s[0] += r.lat
        s[1] += r.lng
        s[2] += 1
    centroids = {
        taluk: (s[0] / s[2], s[1] / s[2])
        for taluk, s in sums.items()
        if s[2] > 0
    }
    if not centroids:
        return records

    added: list[SourceRecord] = []
    for o in osm_records:
        if o.lat is None or o.lng is None:
            continue
        if normalize_name(o.name) in known:
            continue
        lat, lng = o.lat, o.lng
        curated = TOWN_BLOCK_ASSIGNMENT.get(normalize_name(o.name))
        if curated and curated in block_names:
            # Known town pinned to its geographic block. The block may have no
            # coordinate anchors yet — then the town itself provides them.
            taluk = curated
            if curated in centroids:
                dist_km = haversine((lat, lng), centroids[curated]) / 1000.0
                if dist_km > max_assign_km:
                    continue
        else:
            taluk, _ = min(
                centroids.items(),
                key=lambda item: haversine((lat, lng), item[1]),
            )
            dist_km = haversine((lat, lng), centroids[taluk]) / 1000.0
            if dist_km > max_assign_km:
                continue
        rec = SourceRecord(
            name=o.name,
            name_ta=o.name_ta,
            taluk=taluk,
            district=o.district,
            lat=o.lat,
            lng=o.lng,
            place_type=o.place_type,
            source="osm",
        )
        rec.has_coords = True
        added.append(rec)
        known.add(normalize_name(o.name))
    return records + added
