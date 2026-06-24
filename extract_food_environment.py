#!/usr/bin/env python3
"""
Extract food environment infrastructure from OpenStreetMap via Overpass API
for comparative food system ecology analysis in Irish counties.

Outputs GeoJSON FeatureCollections and CSV files per category per county.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_HEADERS = {
    "User-Agent": "CapstoneFoodEcology/1.0 (academic research; Rx One Health 2026)",
}
REQUEST_DELAY_SECONDS = 2

# Irish counties in OSM use "County {Name}" (relation admin_level=6).
# area_id = 3600000000 + relation_id (used for reference; queries resolve via map_to_area).
COUNTIES: dict[str, dict[str, int | str]] = {
    "dublin": {"relation_id": 282800, "area_id": 3600282800, "display_name": "Dublin"},
    "galway": {"relation_id": 335444, "area_id": 3600335444, "display_name": "Galway"},
}

# (export_slug, internal_category_label, overpass_query_body)
# Query bodies use {area_id} placeholder; boundary block prepended at runtime.
CATEGORY_DEFINITIONS: list[tuple[str, str, str]] = [
    (
        "food_service",
        "restaurant",
        """
(
  node["amenity"="restaurant"](area.county);
  way["amenity"="restaurant"](area.county);
  relation["amenity"="restaurant"](area.county);
  node["amenity"="cafe"](area.county);
  way["amenity"="cafe"](area.county);
  relation["amenity"="cafe"](area.county);
  node["amenity"="bar"]["food"="yes"](area.county);
  way["amenity"="bar"]["food"="yes"](area.county);
  relation["amenity"="bar"]["food"="yes"](area.county);
  node["amenity"="pub"]["food"="yes"](area.county);
  way["amenity"="pub"]["food"="yes"](area.county);
  relation["amenity"="pub"]["food"="yes"](area.county);
);
""",
    ),
    (
        "fast_food_takeaway",
        "fast_food",
        """
(
  node["amenity"="fast_food"](area.county);
  way["amenity"="fast_food"](area.county);
  relation["amenity"="fast_food"](area.county);
  node["amenity"="food_court"](area.county);
  way["amenity"="food_court"](area.county);
  relation["amenity"="food_court"](area.county);
  node["shop"="deli"](area.county);
  way["shop"="deli"](area.county);
  relation["shop"="deli"](area.county);
);
""",
    ),
    (
        "food_retail_formal",
        "supermarket",
        """
(
  node["shop"="supermarket"](area.county);
  way["shop"="supermarket"](area.county);
  relation["shop"="supermarket"](area.county);
  node["shop"="convenience"](area.county);
  way["shop"="convenience"](area.county);
  relation["shop"="convenience"](area.county);
  node["shop"="grocery"](area.county);
  way["shop"="grocery"](area.county);
  relation["shop"="grocery"](area.county);
  node["shop"="butcher"](area.county);
  way["shop"="butcher"](area.county);
  relation["shop"="butcher"](area.county);
  node["shop"="bakery"](area.county);
  way["shop"="bakery"](area.county);
  relation["shop"="bakery"](area.county);
  node["shop"="fishmonger"](area.county);
  way["shop"="fishmonger"](area.county);
  relation["shop"="fishmonger"](area.county);
  node["shop"="greengrocer"](area.county);
  way["shop"="greengrocer"](area.county);
  relation["shop"="greengrocer"](area.county);
);
""",
    ),
    (
        "local_markets",
        "local_market",
        """
(
  node["amenity"="marketplace"](area.county);
  way["amenity"="marketplace"](area.county);
  relation["amenity"="marketplace"](area.county);
  node["shop"="farm"](area.county);
  way["shop"="farm"](area.county);
  relation["shop"="farm"](area.county);
  way["landuse"="farmyard"](area.county);
  relation["landuse"="farmyard"](area.county);
  node["craft"]["food"="yes"](area.county);
  way["craft"]["food"="yes"](area.county);
  relation["craft"]["food"="yes"](area.county);
);
""",
    ),
    (
        "primary_production",
        "farm",
        """
(
  way["landuse"="farmland"](area.county);
  relation["landuse"="farmland"](area.county);
  way["landuse"="orchard"](area.county);
  relation["landuse"="orchard"](area.county);
  way["landuse"="allotments"](area.county);
  relation["landuse"="allotments"](area.county);
  way["landuse"="greenhouse_horticulture"](area.county);
  relation["landuse"="greenhouse_horticulture"](area.county);
  way["building"="greenhouse"](area.county);
  relation["building"="greenhouse"](area.county);
);
""",
    ),
    (
        "water",
        "water",
        """
(
  way["natural"="water"](area.county);
  relation["natural"="water"](area.county);
  way["waterway"="river"](area.county);
  relation["waterway"="river"](area.county);
  way["waterway"="stream"](area.county);
  relation["waterway"="stream"](area.county);
  way["waterway"="canal"](area.county);
  relation["waterway"="canal"](area.county);
  way["natural"="wetland"](area.county);
  relation["natural"="wetland"](area.county);
);
""",
    ),
    (
        "waste",
        "waste",
        """
(
  node["amenity"="waste_disposal"](area.county);
  way["amenity"="waste_disposal"](area.county);
  relation["amenity"="waste_disposal"](area.county);
  way["landuse"="landfill"](area.county);
  relation["landuse"="landfill"](area.county);
  node["amenity"="recycling"](area.county);
  way["amenity"="recycling"](area.county);
  relation["amenity"="recycling"](area.county);
  way["man_made"="wastewater_plant"](area.county);
  relation["man_made"="wastewater_plant"](area.county);
);
""",
    ),
]

SUBCATEGORY_PRIORITY: list[tuple[str, str]] = [
    ("amenity", "restaurant"),
    ("amenity", "cafe"),
    ("amenity", "bar"),
    ("amenity", "pub"),
    ("amenity", "fast_food"),
    ("amenity", "food_court"),
    ("shop", "deli"),
    ("shop", "supermarket"),
    ("shop", "convenience"),
    ("shop", "grocery"),
    ("shop", "butcher"),
    ("shop", "bakery"),
    ("shop", "fishmonger"),
    ("shop", "greengrocer"),
    ("amenity", "marketplace"),
    ("shop", "farm"),
    ("landuse", "farmyard"),
    ("craft", "*"),
    ("landuse", "farmland"),
    ("landuse", "orchard"),
    ("landuse", "allotments"),
    ("landuse", "greenhouse_horticulture"),
    ("building", "greenhouse"),
    ("natural", "water"),
    ("waterway", "river"),
    ("waterway", "stream"),
    ("waterway", "canal"),
    ("natural", "wetland"),
    ("amenity", "waste_disposal"),
    ("landuse", "landfill"),
    ("amenity", "recycling"),
    ("man_made", "wastewater_plant"),
]


def build_overpass_query(county_display_name: str, body: str) -> str:
    """Assemble full Overpass QL with official admin boundary and area filter."""
    relation_name = f"County {county_display_name}"
    return f"""[out:json][timeout:120][maxsize:536870912];
relation["name"="{relation_name}"]["admin_level"="6"]["boundary"="administrative"]->.county_rel;
.county_rel map_to_area -> .county;
{body.strip()}
out center;
"""


def infer_subcategory(tags: dict[str, str]) -> str:
    for key, value in SUBCATEGORY_PRIORITY:
        if key not in tags:
            continue
        if value == "*":
            return f"craft={tags[key]}"
        if tags[key] == value:
            return f"{key}={value}"
    for key in ("amenity", "shop", "landuse", "natural", "waterway", "building", "man_made", "craft"):
        if key in tags:
            return f"{key}={tags[key]}"
    return "unknown"


def admin_division_from_tags(tags: dict[str, str]) -> str:
    parts = [
        tags.get("addr:suburb", "").strip(),
        tags.get("addr:city", "").strip(),
        tags.get("addr:county", "").strip(),
    ]
    return ", ".join(p for p in parts if p)


def element_centroid(element: dict[str, Any]) -> tuple[float | None, float | None]:
    if element["type"] == "node":
        return element.get("lat"), element.get("lon")
    center = element.get("center")
    if center:
        return center.get("lat"), center.get("lon")
    lat = element.get("lat")
    lon = element.get("lon")
    if lat is not None and lon is not None:
        return lat, lon
    return None, None


def osm_id_string(element: dict[str, Any]) -> str:
    prefix = element["type"][0]
    return f"{prefix}{element['id']}"


def element_to_record(
    element: dict[str, Any],
    county_slug: str,
    category: str,
) -> dict[str, Any] | None:
    tags = element.get("tags", {})
    lat, lon = element_centroid(element)
    if lat is None or lon is None:
        return None

    return {
        "osm_id": osm_id_string(element),
        "name": tags.get("name", ""),
        "category": category,
        "subcategory": infer_subcategory(tags),
        "lat": lat,
        "lon": lon,
        "admin_division": admin_division_from_tags(tags),
        "county": county_slug,
        "osm_type": element["type"],
        "osm_numeric_id": element["id"],
    }


def fetch_overpass(query: str, retries: int = 3) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.post(
                OVERPASS_URL,
                data={"data": query},
                headers=OVERPASS_HEADERS,
                timeout=180,
            )
            if response.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"  Rate limited; waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, json.JSONDecodeError) as exc:
            last_error = exc
            wait = REQUEST_DELAY_SECONDS * (2**attempt)
            print(f"  Request failed ({exc}); retry in {wait}s...", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"Overpass request failed after {retries} attempts: {last_error}")


def records_to_geojson(records: list[dict[str, Any]]) -> dict[str, Any]:
    features = []
    for rec in records:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [rec["lon"], rec["lat"]]},
                "properties": {
                    "osm_id": rec["osm_id"],
                    "name": rec["name"],
                    "category": rec["category"],
                    "subcategory": rec["subcategory"],
                    "lat": rec["lat"],
                    "lon": rec["lon"],
                    "admin_division": rec["admin_division"],
                    "county": rec["county"],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def write_geojson(path: Path, geojson: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(geojson, fh, ensure_ascii=False, indent=2)


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["osm_id", "name", "category", "subcategory", "lat", "lon", "admin_division"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def extract_category(
    county_slug: str,
    county_display_name: str,
    export_slug: str,
    category_label: str,
    query_body: str,
    output_dir: Path,
    run_date: str,
    save_query: bool,
) -> list[dict[str, Any]]:
    query = build_overpass_query(county_display_name, query_body)
    queries_dir = output_dir / "queries"
    if save_query:
        queries_dir.mkdir(parents=True, exist_ok=True)
        query_path = queries_dir / f"{county_slug}_{export_slug}_{run_date}.overpass"
        query_path.write_text(query, encoding="utf-8")

    print(f"  Fetching {export_slug}...", file=sys.stderr)
    payload = fetch_overpass(query)

    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    skipped = 0
    for element in payload.get("elements", []):
        key = f"{element['type']}/{element['id']}"
        if key in seen:
            continue
        seen.add(key)
        record = element_to_record(element, county_slug, category_label)
        if record is None:
            skipped += 1
            continue
        records.append(record)

    base_name = f"{county_slug}_{export_slug}_{run_date}"
    write_geojson(output_dir / "geojson" / f"{base_name}.geojson", records_to_geojson(records))
    write_csv(output_dir / "csv" / f"{base_name}.csv", records)

    print(f"  {export_slug}: {len(records)} features ({skipped} without centroid skipped)", file=sys.stderr)
    return records


def extract_county(
    county_slug: str,
    output_dir: Path,
    run_date: str,
    categories: list[str] | None,
    save_queries: bool,
) -> dict[str, list[dict[str, Any]]]:
    meta = COUNTIES[county_slug]
    display_name = str(meta["display_name"])
    relation_id = int(meta["relation_id"])
    area_id = int(meta["area_id"])

    print(
        f"\n=== County {display_name} (relation {relation_id}, area {area_id}) ===",
        file=sys.stderr,
    )
    results: dict[str, list[dict[str, Any]]] = {}

    for export_slug, category_label, query_body in CATEGORY_DEFINITIONS:
        if categories and export_slug not in categories:
            continue
        records = extract_category(
            county_slug=county_slug,
            county_display_name=display_name,
            export_slug=export_slug,
            category_label=category_label,
            query_body=query_body,
            output_dir=output_dir,
            run_date=run_date,
            save_query=save_queries,
        )
        results[export_slug] = records
        time.sleep(REQUEST_DELAY_SECONDS)

    return results


def build_panel_index(all_results: dict[str, dict[str, list[dict[str, Any]]]], output_dir: Path, run_date: str) -> None:
    """Merge county outputs into a single panel-ready CSV indexed by county + category + osm_id."""
    panel_path = output_dir / "csv" / f"panel_{run_date}.csv"
    fieldnames = [
        "county",
        "osm_id",
        "name",
        "category",
        "subcategory",
        "lat",
        "lon",
        "admin_division",
    ]
    rows: list[dict[str, Any]] = []
    for county_slug, categories in all_results.items():
        for records in categories.values():
            for rec in records:
                rows.append({k: rec.get(k, "") for k in fieldnames})

    with panel_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nPanel dataset: {panel_path} ({len(rows)} rows)", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract OSM food environment data for Dublin and Galway counties."
    )
    parser.add_argument(
        "--counties",
        nargs="+",
        choices=list(COUNTIES.keys()),
        default=list(COUNTIES.keys()),
        help="Counties to extract (default: both)",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=[c[0] for c in CATEGORY_DEFINITIONS],
        default=None,
        help="Subset of categories to extract (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/extracted"),
        help="Output directory root",
    )
    parser.add_argument(
        "--date",
        default=date.today().strftime("%Y%m%d"),
        help="Date stamp for filenames (YYYYMMDD)",
    )
    parser.add_argument(
        "--save-queries",
        action="store_true",
        help="Save Overpass QL query files alongside outputs",
    )
    parser.add_argument(
        "--no-panel",
        action="store_true",
        help="Skip merged panel CSV export",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    all_results: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for county_slug in args.counties:
        all_results[county_slug] = extract_county(
            county_slug=county_slug,
            output_dir=args.output_dir,
            run_date=args.date,
            categories=args.categories,
            save_queries=args.save_queries,
        )

    if not args.no_panel and len(all_results) > 0:
        build_panel_index(all_results, args.output_dir, args.date)

    print("\nExtraction complete.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
