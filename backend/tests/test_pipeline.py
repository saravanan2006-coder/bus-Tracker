"""Tests for the village data pipeline (merge, reconciliation, CSV parsing)."""
from __future__ import annotations

from app.services.village_pipeline import (
    SourceRecord,
    build_reconciliation_report,
    census_expected_by_taluk,
    enrich_with_osm_coords,
    merge_osm_places,
    merge_village_sources,
    normalize_name,
    parse_census_csv,
    parse_tn_census_csv,
)

CENSUS_CSV = """village,taluk,district,census_code,lat,lng,name_ta
Olakkur,Tindivanam,Villupuram,607101,12.1,79.7,ஒலக்கூர்
Kottakuppam,Tindivanam,Villupuram,607102,12.0,79.8,கொட்டக்குப்பம்
"""


def test_normalize_name():
    assert normalize_name("  Anna  Nagar ") == "anna-nagar"


def test_merge_dedupes_and_osm_coords_win():
    census = SourceRecord(
        name="Olakkur", taluk="Tindivanam", district="Villupuram",
        lat=None, lng=None, census_code="607101", source="census",
    )
    osm = SourceRecord(
        name="Olakkur", taluk="Tindivanam", lat=12.05, lng=79.65, source="osm",
        name_ta="ஒலக்கூர்",
    )
    merged, report = merge_village_sources([census, osm])
    assert len(merged) == 1
    entry = merged[normalize_name("Tindivanam") + ":" + normalize_name("Olakkur")]
    assert entry.lat == 12.05
    assert entry.name_ta == "ஒலக்கூர்"
    assert entry.census_code == "607101"
    assert report.missing_coords == 0


def test_missing_coords_kept_and_flagged():
    rec = SourceRecord(name="NoCoords", taluk="Tindivanam", district="Villupuram")
    merged, report = merge_village_sources([rec])
    assert len(merged) == 1
    assert report.missing_coords == 1
    # Never dropped: village survives without coordinates.


def test_reconciliation_blocks_on_gap():
    recs = [
        SourceRecord(name="A", taluk="Tindivanam"),
        SourceRecord(name="B", taluk="Tindivanam"),
        SourceRecord(name="C", taluk="Villupuram"),
    ]
    merged, _ = merge_village_sources(recs)
    report = build_reconciliation_report(
        "Villupuram", merged, expected_by_taluk={"Tindivanam": 3}
    )
    assert report.blocks_publishing is True
    assert report.merged_by_taluk[normalize_name("Tindivanam")] == 2


def test_reconciliation_passes_when_counts_match():
    recs = [
        SourceRecord(name="A", taluk="Tindivanam"),
        SourceRecord(name="B", taluk="Tindivanam"),
    ]
    merged, _ = merge_village_sources(recs)
    report = build_reconciliation_report(
        "Villupuram", merged, expected_by_taluk={"Tindivanam": 2}
    )
    assert report.blocks_publishing is False


def test_parse_census_csv():
    records = parse_census_csv(CENSUS_CSV)
    assert len(records) == 2
    first = records[0]
    assert first.name == "Olakkur"
    assert first.taluk == "Tindivanam"
    assert first.census_code == "607101"
    assert first.lat == 12.1
    assert first.name_ta == "ஒலக்கூர்"


TN_CSV = """S.No,"District 
Code","District Name","Block
 Code","Block Name","Village
 code","Village Name","Habitation Code","Habitation Name"
1,4,VILLUPURAM,1,KANAI,1,ALUR,1,ALUR
2,4,VILLUPURAM,1,KANAI,1,ALUR,2,ALUR-I
3,4,VILLUPURAM,1,KANAI,2,ARIYUR,1,ARIYUR
4,4,VILLUPURAM,2,GINGEE,1,CHEYYUR,1,CHEYYUR
5,1,KANCHEEPURAM,1,KANCHEEPURAM,1,OTHAKALMANDAPAM,1,OTHAKALMANDAPAM
"""


def test_parse_tn_census_csv_collapses_habitations():
    records = parse_tn_census_csv(TN_CSV, district_code="4")
    # ALUR appears in two habitation rows but must land once; the other
    # district's village is excluded by the scope.
    assert len(records) == 3
    by_name = {r.name: r for r in records}
    assert set(by_name) == {"Alur", "Ariyur", "Cheyyur"}
    assert by_name["Alur"].taluk == "Kanai"
    assert by_name["Alur"].census_code == "1"
    assert by_name["Alur"].source == "tn-census"
    assert by_name["Cheyyur"].taluk == "Gingee"


def test_parse_tn_census_csv_without_scope_keeps_all_districts():
    records = parse_tn_census_csv(TN_CSV)
    assert len(records) == 4


def test_census_expected_by_taluk_counts_every_village():
    recs = [
        SourceRecord(name="A", taluk="Kanai"),
        SourceRecord(name="B", taluk="Kanai"),
        SourceRecord(name="C", taluk="Gingee"),
        SourceRecord(name="NoTaluk"),
    ]
    assert census_expected_by_taluk(recs) == {"Gingee": 1, "Kanai": 2}


def test_enrich_with_osm_coords_attaches_unambiguous_matches():
    census = [
        SourceRecord(name="Olakkur", taluk="Kanai", source="tn-census"),
        SourceRecord(name="Shared", taluk="Kanai", source="tn-census"),
        SourceRecord(name="Already", taluk="Kanai", lat=1.0, lng=2.0, source="tn-census"),
    ]
    osm = [
        SourceRecord(name="Olakkur", lat=12.05, lng=79.65, source="osm", name_ta="ஒலக்கூர்"),
        SourceRecord(name="Shared", lat=11.1, lng=79.1, source="osm"),
        SourceRecord(name="Shared", lat=11.2, lng=79.2, source="osm"),
    ]
    records = enrich_with_osm_coords(census, osm)
    by_name = {r.name: r for r in records}
    assert by_name["Olakkur"].lat == 12.05
    assert by_name["Olakkur"].name_ta == "ஒலக்கூர்"
    assert by_name["Olakkur"].has_coords is True
    # Ambiguous name is left unresolved rather than pinned to the wrong point.
    assert by_name["Shared"].lat is None
    assert by_name["Already"].lat == 1.0


def test_merge_osm_places_adds_unmatched_towns():
    census = [
        SourceRecord(name="Olakkur", taluk="Kanai", lat=12.0, lng=79.5, source="tn-census"),
        SourceRecord(name="Cheyyur", taluk="Gingee", lat=12.25, lng=79.4, source="tn-census"),
    ]
    osm = [
        SourceRecord(name="Olakkur", lat=12.0, lng=79.5, source="osm"),  # already in census
        SourceRecord(name="Cheyyur", lat=12.25, lng=79.41, source="osm"),  # already in census
        SourceRecord(name="Aarani", lat=12.28, lng=79.38, place_type="town", source="osm"),
        SourceRecord(name="Faraway", lat=9.5, lng=78.1, source="osm"),  # out of range
    ]
    records = merge_osm_places(census, osm)
    by_name = {r.name: r for r in records}
    # Census records untouched; existing names are never duplicated.
    assert len(records) == 3
    assert by_name["Olakkur"].taluk == "Kanai"
    # New town assigned to the nearest block centroid (Gingee) with coords.
    assert by_name["Aarani"].taluk == "Gingee"
    assert by_name["Aarani"].place_type == "town"
    assert by_name["Aarani"].has_coords is True
    assert by_name["Aarani"].lat == 12.28
    # Out-of-bounds place skipped, never dropped-and-counted.
    assert "Faraway" not in by_name


def test_merge_osm_places_skips_duplicates_but_keeps_census():
    census = [
        SourceRecord(name="Olakkur", taluk="Kanai", lat=12.05, lng=79.65, source="tn-census"),
    ]
    osm = [
        SourceRecord(name="Olakkur", lat=12.05, lng=79.65, source="osm"),
        SourceRecord(name="Olakkur", lat=12.04, lng=79.66, source="osm"),
    ]
    records = merge_osm_places(census, osm)
    assert len(records) == 1
    assert records[0].name == "Olakkur"


def test_merge_osm_places_no_coords_returns_unchanged():
    census = [
        SourceRecord(name="A", taluk="Kanai", lat=12.0, lng=79.5, source="tn-census"),
        SourceRecord(name="B", taluk="Kanai", source="tn-census"),
    ]
    # No coordinates anywhere: no centroids, so nothing new can be placed.
    records = merge_osm_places(
        census, [SourceRecord(name="Town", lat=None, lng=None, source="osm")]
    )
    assert [r.name for r in records] == ["A", "B"]


def test_merge_osm_places_curated_block_wins_for_known_towns():
    census = [
        SourceRecord(name="Cheyyur", taluk="Gingee", lat=12.25, lng=79.4, source="tn-census"),
        SourceRecord(name="Mailam", taluk="Mailam", lat=12.12, lng=79.63, source="tn-census"),
        SourceRecord(name="Sithamur", taluk="Vikkiravandi", lat=11.9, lng=79.53, source="tn-census"),
    ]
    # Villupuram is curated to Vikkiravandi even though the Mailam centroid is
    # geographically nearer than any Vikkiravandi census point.
    osm = [SourceRecord(name="Villupuram", lat=11.94, lng=79.49, place_type="town", source="osm")]
    records = merge_osm_places(census, osm)
    by_name = {r.name: r for r in records}
    assert by_name["Villupuram"].taluk == "Vikkiravandi"
    assert by_name["Villupuram"].lat == 11.94


def test_merge_osm_places_curated_block_without_anchors():
    # Sankarapuram block exists in the census but none of its villages have
    # coordinates yet; the town must still land in its own block.
    census = [
        SourceRecord(name="Soorapattu", taluk="Sankarapuram", source="tn-census"),
        SourceRecord(name="Chinnasalem", taluk="Chinnasalem", lat=11.67, lng=78.87, source="tn-census"),
    ]
    osm = [SourceRecord(name="Sankarapuram", lat=11.887, lng=78.916, place_type="town", source="osm")]
    records = merge_osm_places(census, osm)
    by_name = {r.name: r for r in records}
    assert by_name["Sankarapuram"].taluk == "Sankarapuram"
    assert by_name["Sankarapuram"].has_coords is True
