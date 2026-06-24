#!/usr/bin/env python3
"""Comparative food environment dashboard for Dublin and Galway."""

from __future__ import annotations

import io
import math
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from branca.element import MacroElement
from folium.plugins import HeatMap
from jinja2 import Template

DATA_DIR = Path(__file__).parent / "data" / "extracted" / "csv"

CATEGORY_META = {
    "restaurant": {
        "label": "Food Service",
        "color": "#E74C3C",
        "fa_icon": "fa-utensils",
    },
    "fast_food": {
        "label": "Fast Food & Takeaway",
        "color": "#F39C12",
        "fa_icon": "fa-burger",
    },
    "supermarket": {
        "label": "Formal Food Retail",
        "color": "#27AE60",
        "fa_icon": "fa-cart-shopping",
    },
    "local_market": {
        "label": "Local Markets",
        "color": "#16A085",
        "fa_icon": "fa-store",
    },
    "farm": {
        "label": "Primary Production",
        "color": "#8E44AD",
        "fa_icon": "fa-wheat-awn",
    },
    "water": {
        "label": "Water Infrastructure",
        "color": "#3498DB",
        "fa_icon": "fa-water",
    },
    "waste": {
        "label": "Waste & Disposal",
        "color": "#7F8C8D",
        "fa_icon": "fa-recycle",
    },
}

COUNTY_META = {
    "dublin": {
        "label": "Dublin",
        "city_lat": 53.3498,
        "city_lon": -6.2603,
        "area_km2": 922,
    },
    "galway": {
        "label": "Galway",
        "city_lat": 53.2707,
        "city_lon": -9.0568,
        "area_km2": 6149,
    },
}

CATEGORY_ORDER = list(CATEGORY_META.keys())
DEFAULT_CATEGORIES = ["fast_food", "local_market", "farm"]
DEFAULT_SUBCATEGORIES = ["shop=butcher", "shop=greengrocer", "landuse=farmland"]
DEFAULT_RADIUS_KM = 5
MARKER_PX = 20
MARKER_ICON_PX = 11
SUBCATEGORY_MARKER_PX = 24
SUBCATEGORY_MARKER_ICON_PX = 13
POINT_MAP_HEIGHT = 520
HEATMAP_MAP_HEIGHT = 480
CHART_TITLE_TOP_MARGIN = 72

ACCESS_TIER = {
    "supermarket": "healthy",
    "local_market": "healthy",
    "farm": "healthy",
    "fast_food": "unhealthy",
    "restaurant": "mixed",
    "water": "infrastructure",
    "waste": "infrastructure",
}

ACCESS_TIER_META = {
    "healthy": {"label": "Healthy access", "color": "#27AE60"},
    "unhealthy": {"label": "Unhealthy access", "color": "#E67E22"},
    "mixed": {"label": "Mixed / other food service", "color": "#E74C3C"},
    "infrastructure": {"label": "Ecological infrastructure", "color": "#95A5A6"},
}

FOOD_ACCESS_CATEGORIES = ["supermarket", "local_market", "farm", "fast_food", "restaurant"]

OSM_SUBCATEGORIES = {
    "restaurant": "amenity=bar, amenity=cafe, amenity=pub, amenity=restaurant",
    "fast_food": "amenity=bar, amenity=cafe, amenity=fast_food, amenity=food_court, shop=deli",
    "supermarket": (
        "amenity=cafe, amenity=fast_food, amenity=restaurant, shop=bakery, shop=butcher, "
        "shop=convenience, shop=greengrocer, shop=grocery, shop=supermarket"
    ),
    "local_market": "amenity=marketplace, landuse=farmyard",
    "farm": "building=greenhouse, landuse=allotments, landuse=farmland, landuse=greenhouse_horticulture",
    "water": "natural=water, natural=wetland, waterway=canal, waterway=river, waterway=stream",
    "waste": "amenity=recycling, amenity=waste_disposal, man_made=wastewater_plant",
}

SUBCATEGORY_FA_ICONS = {
    "amenity=bar": "martini-glass",
    "amenity=cafe": "mug-saucer",
    "amenity=fast_food": "burger",
    "amenity=food_court": "bowl-food",
    "amenity=marketplace": "store",
    "amenity=pub": "beer-mug-empty",
    "amenity=recycling": "recycle",
    "amenity=restaurant": "utensils",
    "amenity=waste_disposal": "dumpster",
    "building=greenhouse": "seedling",
    "landuse=allotments": "carrot",
    "landuse=farmland": "wheat-awn",
    "landuse=farmyard": "cow",
    "landuse=greenhouse_horticulture": "leaf",
    "landuse=landfill": "trash",
    "landuse=orchard": "apple-whole",
    "man_made=wastewater_plant": "faucet-drip",
    "natural=water": "water",
    "natural=wetland": "droplet",
    "shop=bakery": "bread-slice",
    "shop=butcher": "drumstick-bite",
    "shop=convenience": "store",
    "shop=deli": "cheese",
    "shop=farm": "barn",
    "shop=greengrocer": "apple-whole",
    "shop=grocery": "basket-shopping",
    "shop=supermarket": "cart-shopping",
    "waterway=canal": "ship",
    "waterway=river": "water",
    "waterway=stream": "droplet",
}

METRIC_DEFINITIONS = [
    (
        "healthy_points",
        "Healthy access points",
        "Count of features classified as healthy access: formal food retail, local markets, "
        "and primary production within the selected urban buffer.",
    ),
    (
        "unhealthy_points",
        "Unhealthy access points",
        "Count of fast food and food court features within the urban buffer.",
    ),
    (
        "mixed_points",
        "Mixed food service points",
        "Count of sit-down food service features (restaurants, cafés, pubs) within the buffer.",
    ),
    (
        "healthy_share_pct",
        "Healthy share (%)",
        "Healthy access points divided by all food-access points (healthy + unhealthy + mixed), × 100.",
    ),
    (
        "unhealthy_share_pct",
        "Unhealthy share (%)",
        "Unhealthy access points divided by all food-access points, × 100.",
    ),
    (
        "healthy_unhealthy_ratio",
        "Healthy / unhealthy ratio",
        "Healthy access points divided by unhealthy access points. Higher values indicate more "
        "healthy relative to unhealthy outlets.",
    ),
    (
        "healthy_density",
        "Healthy density (per km²)",
        "Healthy access points divided by the buffer area (π × radius²).",
    ),
    (
        "unhealthy_density",
        "Unhealthy density (per km²)",
        "Unhealthy access points divided by the buffer area (π × radius²).",
    ),
]

CUSTOM_CSS = """
<style>
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #FFFFFF !important;
    }
    [data-testid="stMain"] {
        background-color: #FFFFFF !important;
    }
    span[data-baseweb="tag"] {
        background-color: #2563eb !important;
        border: 1px solid #1d4ed8 !important;
    }
    span[data-baseweb="tag"] span {
        color: #FFFFFF !important;
    }
    span[data-baseweb="tag"] svg {
        fill: #FFFFFF !important;
    }
    .map-legend-wrap {
        background: #F5F7FA;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 10px 16px;
        margin-bottom: 12px;
    }
    .map-legend-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #334155;
        margin-bottom: 8px;
    }
    .map-legend-items {
        display: flex;
        flex-wrap: wrap;
        gap: 14px 22px;
        align-items: center;
    }
    .map-legend-item {
        display: flex;
        align-items: center;
        gap: 7px;
        font-size: 0.82rem;
        color: #1E293B;
    }
    .map-legend-icon {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 1px solid rgba(255,255,255,0.9);
        box-shadow: 0 0 0 1px rgba(0,0,0,0.12);
        flex-shrink: 0;
    }
    .map-legend-icon i {
        font-size: 8px;
        line-height: 1;
    }
    .subcategory-ref {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 12px 0 16px 0;
        font-size: 0.84rem;
        color: #334155;
    }
    .subcategory-ref h4 {
        margin: 0 0 8px 0;
        font-size: 0.9rem;
        color: #1E293B;
    }
    .subcategory-ref ul {
        margin: 0;
        padding-left: 18px;
    }
    .subcategory-ref li {
        margin-bottom: 6px;
    }
    .chart-dl-spacer {
        margin-top: 6px;
    }
    .chart-block-gap {
        margin-bottom: 1.25rem;
    }
    .heatmap-cat-title {
        font-size: 0.92rem;
        font-weight: 600;
        color: #1E293B;
        margin: 14px 0 6px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .heatmap-cat-title .cat-icon {
        width: 22px;
        height: 22px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: #FFFFFF;
        font-size: 10px;
        flex-shrink: 0;
    }
    .tab-hint {
        font-size: 0.85rem;
        color: #64748B;
        margin-bottom: 8px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #E2E8F0 !important;
        color: #334155 !important;
        border-radius: 8px 8px 0 0 !important;
        padding: 10px 20px !important;
        font-weight: 600 !important;
        border: 2px solid #CBD5E1 !important;
        border-bottom: none !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2563eb !important;
        color: #FFFFFF !important;
        border-color: #1d4ed8 !important;
    }
    .metric-definitions {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 12px 16px;
        margin-top: 10px;
        font-size: 0.92rem;
        color: #475569;
        line-height: 1.55;
    }
    .metric-definitions h4 {
        margin: 0 0 10px 0;
        font-size: 1rem;
        color: #1E293B;
    }
    .metric-definitions p {
        margin: 6px 0;
    }
    .stats-table-wrap {
        margin: 8px 0 16px 0;
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #CBD5E1;
    }
    .stats-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 1.05rem;
    }
    .stats-table th {
        background-color: #2563eb;
        color: #FFFFFF;
        padding: 14px 18px;
        text-align: left;
        font-size: 1.12rem;
        font-weight: 600;
    }
    .stats-table td {
        padding: 12px 18px;
        border-bottom: 1px solid #E2E8F0;
        color: #1E293B;
    }
    .stats-table tbody tr:last-child td {
        border-bottom: none;
    }
    .stats-table td:first-child {
        font-weight: 600;
        background-color: #F8FAFC;
        width: 38%;
    }
    .stats-table tbody tr:hover td {
        background-color: #EFF6FF;
    }
    .stats-table tbody tr:hover td:first-child {
        background-color: #DBEAFE;
    }
    .map-frame {
        border: 2px solid #CBD5E1;
        border-radius: 16px;
        overflow: hidden;
        margin-bottom: 8px;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
    }
    .map-frame iframe {
        border-radius: 14px !important;
        display: block;
    }
    .dashboard-title-main {
        font-size: clamp(2.2rem, 4.5vw, 3.75rem);
        font-weight: 800;
        color: #0F172A;
        margin: 0;
        line-height: 1.08;
        letter-spacing: -0.02em;
    }
    .dashboard-title-sub {
        font-size: clamp(1.85rem, 3.5vw, 3rem);
        font-weight: 700;
        color: #2563eb !important;
        margin: 0.02em 0 1rem 0;
        line-height: 1.08;
        letter-spacing: -0.01em;
    }
    .dashboard-header-block {
        margin-bottom: 0.5rem;
    }
    .heatmap-math {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 14px 18px;
        margin: 16px 0;
        font-size: 0.9rem;
        color: #334155;
        line-height: 1.6;
    }
    .heatmap-math h4 {
        margin: 0 0 10px 0;
        color: #1E293B;
    }
    .heatmap-math code, .heatmap-math .formula {
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        background: #EEF2FF;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.88rem;
    }
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css"/>
"""


@st.cache_data
def load_panel() -> pd.DataFrame:
    panel_files = sorted(DATA_DIR.glob("panel_*.csv"), reverse=True)
    if not panel_files:
        raise FileNotFoundError(f"No panel CSV found in {DATA_DIR}")
    df = pd.read_csv(panel_files[0])
    df["category"] = pd.Categorical(df["category"], categories=CATEGORY_ORDER, ordered=True)
    df["county_label"] = df["county"].map(lambda c: COUNTY_META[c]["label"])
    df["category_label"] = df["category"].map(lambda c: CATEGORY_META[c]["label"])
    df["category_color"] = df["category"].map(lambda c: CATEGORY_META[c]["color"])
    df["access_tier"] = df["category"].map(ACCESS_TIER)
    df["access_tier_label"] = df["access_tier"].map(lambda t: ACCESS_TIER_META[t]["label"])
    return df


def format_subcategory_label(subcategory: str) -> str:
    value = subcategory.split("=", 1)[1] if "=" in subcategory else subcategory
    return value.replace("_", " ").title()


def format_osm_tag_list(tags_str: str) -> str:
    return ", ".join(format_subcategory_label(part.strip()) for part in tags_str.split(","))


def filter_by_subcategories(df: pd.DataFrame, subcategories: list[str]) -> pd.DataFrame:
    return df[df["subcategory"].isin(subcategories)].copy()


def subcategory_options(df: pd.DataFrame) -> list[str]:
    return sorted(df["subcategory"].unique(), key=format_subcategory_label)


def filter_data(df: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    return df[df["category"].isin(categories)].copy()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.asin(math.sqrt(a))


def filter_by_city_radius(df: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for county in ["dublin", "galway"]:
        sub = df[df["county"] == county].copy()
        if sub.empty:
            continue
        meta = COUNTY_META[county]
        clat, clon = meta["city_lat"], meta["city_lon"]
        sub["distance_km"] = sub.apply(
            lambda row: haversine_km(clat, clon, row["lat"], row["lon"]),
            axis=1,
        )
        parts.append(sub[sub["distance_km"] <= radius_km])
    if not parts:
        return df.iloc[0:0].copy()
    return pd.concat(parts, ignore_index=True)


def circle_bounds(lat: float, lon: float, radius_km: float) -> list[list[float]]:
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * math.cos(math.radians(lat)))
    return [[lat - dlat, lon - dlon], [lat + dlat, lon + dlon]]


def zoom_for_buffer(lat: float, radius_km: float, map_height_px: int) -> int:
    """Leaflet zoom level so the urban-buffer circle fits the map panel."""
    margin = 1.08
    diameter_m = 2 * radius_km * 1000 * margin
    lat_rad = math.radians(lat)
    ground_resolution_z0 = 156543.03392 * math.cos(lat_rad)
    viewport_px = map_height_px * 0.9
    zoom = math.log2(ground_resolution_z0 * viewport_px / diameter_m)
    return int(max(10, min(15, round(zoom))))


def buffer_area_km2(radius_km: float) -> float:
    return math.pi * radius_km**2


def _category_fa_name(category: str) -> str:
    fa_icon = CATEGORY_META[category]["fa_icon"]
    return fa_icon[3:] if fa_icon.startswith("fa-") else fa_icon


def subcategory_fa_name(subcategory: str, category: str) -> str:
    return SUBCATEGORY_FA_ICONS.get(subcategory, _category_fa_name(category))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _rgb_to_hex(red: int, green: int, blue: int) -> str:
    return f"#{red:02x}{green:02x}{blue:02x}"


def _mix_hex(base: str, target: str, weight: float) -> str:
    weight = max(0.0, min(1.0, weight))
    br, bg, bb = _hex_to_rgb(base)
    tr, tg, tb = _hex_to_rgb(target)
    return _rgb_to_hex(
        int(br + (tr - br) * weight),
        int(bg + (tg - bg) * weight),
        int(bb + (tb - bb) * weight),
    )


def subcategory_marker_colors(subcategory: str, category: str) -> tuple[str, str]:
    """Return background and icon colors as distinct tones within the category palette."""
    base = CATEGORY_META[category]["color"]
    subcat_index = sum(ord(ch) for ch in subcategory) % 5
    tint_shift = 0.04 * subcat_index
    bg_color = _mix_hex(base, "#FFFFFF", 0.62 + tint_shift)
    icon_color = _mix_hex(base, "#000000", 0.28 + tint_shift * 0.5)
    return bg_color, icon_color


def _div_icon(
    fa_name: str,
    bg_color: str,
    icon_color: str = "#FFFFFF",
    marker_px: int = MARKER_PX,
    icon_px: int = MARKER_ICON_PX,
    border_color: str = "#FFFFFF",
    border_width: int = 1,
) -> folium.DivIcon:
    html = f"""
    <div style="
        background-color:{bg_color};
        width:{marker_px}px;
        height:{marker_px}px;
        border-radius:50%;
        border:{border_width}px solid {border_color};
        display:flex;
        align-items:center;
        justify-content:center;
        box-shadow:0 0 0 1px rgba(0,0,0,0.15);
    ">
        <i class="fa-solid fa-{fa_name}" style="color:{icon_color};font-size:{icon_px}px;line-height:1;"></i>
    </div>
    """
    return folium.DivIcon(
        html=html,
        icon_size=(marker_px, marker_px),
        icon_anchor=(marker_px // 2, marker_px // 2),
        class_name="empty",
    )


def category_div_icon(cat: str) -> folium.DivIcon:
    meta = CATEGORY_META[cat]
    return _div_icon(_category_fa_name(cat), meta["color"], "#FFFFFF")


def subcategory_div_icon(subcategory: str, category: str) -> folium.DivIcon:
    bg_color, icon_color = subcategory_marker_colors(subcategory, category)
    ring_color = CATEGORY_META[category]["color"]
    return _div_icon(
        subcategory_fa_name(subcategory, category),
        bg_color,
        icon_color,
        marker_px=SUBCATEGORY_MARKER_PX,
        icon_px=SUBCATEGORY_MARKER_ICON_PX,
        border_color=ring_color,
        border_width=2,
    )


def _fa_class(fa_icon: str) -> str:
    return fa_icon if fa_icon.startswith("fa-") else f"fa-{fa_icon}"


def render_map_legend_html(active_categories: list[str]) -> str:
    items = []
    for cat in CATEGORY_ORDER:
        if cat not in active_categories:
            continue
        meta = CATEGORY_META[cat]
        fa_name = _fa_class(meta["fa_icon"])
        fa_name = fa_name[3:] if fa_name.startswith("fa-") else fa_name
        items.append(
            f'<div class="map-legend-item">'
            f'<span class="map-legend-icon" style="background-color:{meta["color"]};">'
            f'<i class="fa-solid fa-{fa_name}" style="color:#FFFFFF;"></i>'
            f"</span>"
            f"<span>{meta['label']}</span>"
            f"</div>"
        )
    return (
        '<div class="map-legend-wrap">'
        '<div class="map-legend-title">Categories</div>'
        f'<div class="map-legend-items">{"".join(items)}</div>'
        "</div>"
    )


def _inject_fontawesome(m: folium.Map) -> None:
    m.get_root().header.add_child(
        folium.Element(
            '<link rel="stylesheet" '
            'href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css"/>'
        )
    )


class LockMapView(MacroElement):
    """Re-apply centre/zoom after embed (fixes max-zoom in Streamlit HTML iframes)."""

    _template = Template("""
    {% macro script(this, kwargs) %}
        (function () {
            var map = {{ this._parent.get_name() }};
            var center = [{{ this.lat }}, {{ this.lon }}];
            var zoom = {{ this.zoom }};
            function applyView() {
                map.invalidateSize({ animate: false, pan: false });
                map.setView(center, zoom, { animate: false });
            }
            map.whenReady(applyView);
            setTimeout(applyView, 150);
            setTimeout(applyView, 450);
        })();
    {% endmacro %}
    """)

    def __init__(self, lat: float, lon: float, zoom: int):
        super().__init__()
        self.lat = lat
        self.lon = lon
        self.zoom = zoom


def _static_map_base(county: str, radius_km: float, map_height_px: int) -> folium.Map:
    meta = COUNTY_META[county]
    city_lat, city_lon = meta["city_lat"], meta["city_lon"]
    zoom = zoom_for_buffer(city_lat, radius_km, map_height_px)

    m = folium.Map(
        location=[city_lat, city_lon],
        zoom_start=zoom,
        tiles="OpenStreetMap",
        zoom_control=True,
        scrollWheelZoom=False,
        dragging=False,
        doubleClickZoom=False,
        boxZoom=False,
        keyboard=False,
        touchZoom=False,
    )
    _inject_fontawesome(m)

    folium.Circle(
        location=[city_lat, city_lon],
        radius=radius_km * 1000,
        color="#2563eb",
        weight=2,
        fill=True,
        fill_color="#2563eb",
        fill_opacity=0.08,
        tooltip=f"{radius_km} km urban buffer",
    ).add_to(m)

    folium.Marker(
        location=[city_lat, city_lon],
        tooltip=f"{meta['label']} city centre",
        icon=folium.Icon(color="blue", icon="home", prefix="fa"),
    ).add_to(m)

    LockMapView(city_lat, city_lon, zoom).add_to(m)
    return m


def render_osm_subcategories_html() -> str:
    blocks = [
        '<div class="subcategory-ref">'
        "<h4>OSM subcategories within the urban buffer</h4>"
        "<p>Each tag shows the OpenStreetMap key=value pair; only the value is used in filters and charts below.</p>"
        "<ul>"
    ]
    for cat in CATEGORY_ORDER:
        label = CATEGORY_META[cat]["label"]
        tags = format_osm_tag_list(OSM_SUBCATEGORIES[cat])
        blocks.append(f"<li><strong>{label}:</strong> {tags}</li>")
    blocks.append("</ul></div>")
    return "".join(blocks)


def render_subcategory_map_legend_html(
    df: pd.DataFrame,
    active_subcategories: list[str],
) -> str:
    subcat_to_cat = (
        df.drop_duplicates("subcategory")
        .set_index("subcategory")["category"]
        .to_dict()
    )
    items = []
    for subcat in sorted(active_subcategories, key=format_subcategory_label):
        cat = subcat_to_cat.get(subcat)
        if not cat:
            continue
        fa_name = subcategory_fa_name(subcat, cat)
        bg_color, icon_color = subcategory_marker_colors(subcat, cat)
        items.append(
            f'<div class="map-legend-item">'
            f'<span class="map-legend-icon" style="background-color:{bg_color};">'
            f'<i class="fa-solid fa-{fa_name}" style="color:{icon_color};"></i>'
            f"</span>"
            f"<span>{format_subcategory_label(subcat)}</span>"
            f"</div>"
        )
    return (
        '<div class="map-legend-wrap">'
        '<div class="map-legend-title">Subcategories</div>'
        f'<div class="map-legend-items">{"".join(items)}</div>'
        "</div>"
    )


def render_category_title_html(category: str) -> str:
    meta = CATEGORY_META[category]
    fa_name = meta["fa_icon"][3:] if meta["fa_icon"].startswith("fa-") else meta["fa_icon"]
    return (
        f'<p class="heatmap-cat-title">'
        f'<span class="cat-icon" style="background-color:{meta["color"]};">'
        f'<i class="fa-solid fa-{fa_name}"></i></span>'
        f"<span>{meta['label']}</span></p>"
    )


def build_comparative_stats_table(summary: pd.DataFrame) -> pd.DataFrame:
    dublin = summary.loc[summary["county"] == "dublin"].iloc[0]
    galway = summary.loc[summary["county"] == "galway"].iloc[0]
    rows = []
    for key, label, _ in METRIC_DEFINITIONS:
        d_val = dublin[key]
        g_val = galway[key]
        if key.endswith("_pct"):
            d_fmt = f"{d_val}%"
            g_fmt = f"{g_val}%"
        elif key == "healthy_unhealthy_ratio":
            d_fmt = d_val if pd.notna(d_val) else "N/A"
            g_fmt = g_val if pd.notna(g_val) else "N/A"
        elif isinstance(d_val, float):
            d_fmt = f"{d_val:.2f}"
            g_fmt = f"{g_val:.2f}"
        else:
            d_fmt = f"{int(d_val):,}"
            g_fmt = f"{int(g_val):,}"
        rows.append({"Metric": label, "Dublin": d_fmt, "Galway": g_fmt})
    return pd.DataFrame(rows)


def render_stats_table_html(summary: pd.DataFrame) -> str:
    table_df = build_comparative_stats_table(summary)
    body_rows = []
    for _, row in table_df.iterrows():
        body_rows.append(
            f"<tr><td>{row['Metric']}</td><td>{row['Dublin']}</td><td>{row['Galway']}</td></tr>"
        )
    return (
        '<div class="stats-table-wrap">'
        '<table class="stats-table">'
        "<thead><tr><th>Metric</th><th>Dublin</th><th>Galway</th></tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def render_metric_definitions_html(radius_km: float) -> str:
    lines = [
        "<h4>How each metric is constructed</h4>",
        f"<p>All metrics use a circular urban buffer of <strong>{radius_km:g} km</strong> "
        f"from each city centre (area ≈ {buffer_area_km2(radius_km):.1f} km²).</p>",
    ]
    for _, label, definition in METRIC_DEFINITIONS:
        lines.append(f"<p>- <strong>{label}:</strong> {definition}</p>")
    return f'<div class="metric-definitions">{"".join(lines)}</div>'


def compute_subcategory_density_summary(df: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    area = buffer_area_km2(radius_km)
    radius_df = filter_by_city_radius(df, radius_km)
    rows = []
    for subcat in subcategory_options(radius_df):
        dub_count = int(
            ((radius_df["county"] == "dublin") & (radius_df["subcategory"] == subcat)).sum()
        )
        gal_count = int(
            ((radius_df["county"] == "galway") & (radius_df["subcategory"] == subcat)).sum()
        )
        rows.append(
            {
                "Subcategory": format_subcategory_label(subcat),
                "Dublin": round(dub_count / area, 2),
                "Galway": round(gal_count / area, 2),
            }
        )
    return pd.DataFrame(rows)


def compute_subcategory_density_top10(
    df: pd.DataFrame,
    radius_km: float,
    top_n: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = compute_subcategory_density_summary(df, radius_km)
    dublin_top = summary.nlargest(top_n, "Dublin")[["Subcategory", "Dublin"]].reset_index(drop=True)
    galway_top = summary.nlargest(top_n, "Galway")[["Subcategory", "Galway"]].reset_index(drop=True)
    return dublin_top, galway_top


def render_subcategory_density_table_html(
    dublin_top: pd.DataFrame,
    galway_top: pd.DataFrame,
    radius_km: float,
    top_n: int = 10,
) -> str:
    def _rows(table: pd.DataFrame, value_col: str) -> str:
        body = []
        for _, row in table.iterrows():
            body.append(
                f"<tr><td>{row['Subcategory']}</td>"
                f"<td>{row[value_col]:.2f}</td></tr>"
            )
        return "".join(body)

    return (
        '<div class="metric-definitions">'
        f"<p>Top {top_n} subcategories by point density within a <strong>{radius_km:g} km</strong> "
        f"urban buffer (area ≈ {buffer_area_km2(radius_km):.1f} km²).</p>"
        f"</div>"
        '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;">'
        '<div class="stats-table-wrap" style="flex:1;min-width:280px;">'
        '<table class="stats-table">'
        f"<thead><tr><th>Subcategory</th><th>Dublin (per km²)</th></tr></thead>"
        f"<tbody>{_rows(dublin_top, 'Dublin')}</tbody>"
        "</table></div>"
        '<div class="stats-table-wrap" style="flex:1;min-width:280px;">'
        '<table class="stats-table">'
        f"<thead><tr><th>Subcategory</th><th>Galway (per km²)</th></tr></thead>"
        f"<tbody>{_rows(galway_top, 'Galway')}</tbody>"
        "</table></div>"
        "</div>"
    )


def build_category_subcategory_donut(
    df: pd.DataFrame,
    county: str,
    category: str,
) -> go.Figure:
    county_df = df[(df["county"] == county) & (df["category"] == category)]
    subcats = county_df["subcategory"].unique()
    label_map = {subcat: format_subcategory_label(subcat) for subcat in subcats}
    title = f"{COUNTY_META[county]['label']} — {CATEGORY_META[category]['label']}"
    return build_donut(
        county_df["subcategory"],
        title,
        label_map=label_map,
        color_map=None,
    )


def render_heatmap_methodology_html() -> str:
    return """
<div class="heatmap-math">
<h4>How are point clouds estimated (kernel density heatmap)?</h4>
<p>Each OSM feature is a point <span class="formula">pᵢ = (latᵢ, lonᵢ)</span>.
The heatmap builds a smooth density surface by summing Gaussian kernels centred on every point.</p>
<p><strong>Standard isotropic kernel</strong> (Leaflet.heat / Folium HeatMap):</p>
<p><span class="formula">K(p, pᵢ) = exp(−||p − pᵢ||² / (2σ²))</span></p>
<p><strong>Intensity at location p:</strong></p>
<p><span class="formula">λ(p) = Σᵢ K(p, pᵢ)</span></p>
<p>Parameters used here: <strong>radius = 18 px</strong> (influence radius on screen),
<strong>blur = 14 px</strong> (Gaussian smoothing). Values are min–max normalised to a colour gradient
(low → high density). Overlapping points produce hotter (darker) areas; isolated points produce small local peaks.</p>
<p>This is a <em>visual density estimate</em>, not a formal statistical model. It highlights spatial clusters
of food infrastructure within the selected urban buffer.</p>
</div>
"""


@st.cache_data(show_spinner=False)
def prepare_heatmap_county_json(df: pd.DataFrame, radius_km: float, county: str) -> str:
    radius_all = filter_by_city_radius(df, radius_km)
    return radius_all[radius_all["county"] == county].to_json()


def warm_heatmap_cache(df: pd.DataFrame, radius_km: float) -> tuple[str, str]:
    dublin_json = prepare_heatmap_county_json(df, radius_km, "dublin")
    galway_json = prepare_heatmap_county_json(df, radius_km, "galway")
    for county, county_json in (("dublin", dublin_json), ("galway", galway_json)):
        for cat in CATEGORY_ORDER:
            build_category_heatmap_cached(county, cat, county_json, radius_km)
    return dublin_json, galway_json


@st.cache_data(show_spinner="Building map...")
def build_county_folium_map_cached(
    county: str,
    data_signature: str,
    categories: tuple[str, ...],
    radius_km: float,
) -> str:
    df = pd.read_json(io.StringIO(data_signature))
    m = build_county_folium_map(df, county, list(categories), radius_km)
    return folium_to_html(m)


def build_county_folium_map(
    df: pd.DataFrame,
    county: str,
    active_categories: list[str],
    radius_km: float,
) -> folium.Map:
    county_df = df[df["county"] == county].copy()
    meta = COUNTY_META[county]
    city_lat, city_lon = meta["city_lat"], meta["city_lon"]
    m = _static_map_base(county, radius_km, POINT_MAP_HEIGHT)

    if county_df.empty:
        folium.Marker(
            [city_lat, city_lon],
            tooltip="No features match the current filters within this radius",
            icon=folium.Icon(color="gray", icon="info-sign"),
        ).add_to(m)
        return m

    for cat in CATEGORY_ORDER:
        if cat not in active_categories:
            continue
        sub = county_df[county_df["category"] == cat]
        if sub.empty:
            continue
        cat_meta = CATEGORY_META[cat]
        icon = category_div_icon(cat)
        fg = folium.FeatureGroup(name=cat_meta["label"], show=True)
        for row in sub.itertuples(index=False):
            name = row.name if pd.notna(row.name) and str(row.name).strip() else "(unnamed)"
            tip = (
                f"{name} | {cat_meta['label']} | "
                f"{format_subcategory_label(row.subcategory)} | {row.distance_km:.1f} km"
            )
            folium.Marker(
                location=[row.lat, row.lon],
                tooltip=tip,
                icon=icon,
            ).add_to(fg)
        fg.add_to(m)

    return m


@st.cache_data(show_spinner="Building map...")
def build_county_folium_map_subcat_cached(
    county: str,
    data_signature: str,
    subcategories: tuple[str, ...],
    radius_km: float,
) -> str:
    df = pd.read_json(io.StringIO(data_signature))
    m = build_county_folium_map_subcategories(df, county, list(subcategories), radius_km)
    return folium_to_html(m)


def build_county_folium_map_subcategories(
    df: pd.DataFrame,
    county: str,
    active_subcategories: list[str],
    radius_km: float,
) -> folium.Map:
    county_df = df[
        (df["county"] == county) & (df["subcategory"].isin(active_subcategories))
    ].copy()
    meta = COUNTY_META[county]
    city_lat, city_lon = meta["city_lat"], meta["city_lon"]
    m = _static_map_base(county, radius_km, POINT_MAP_HEIGHT)

    if county_df.empty:
        folium.Marker(
            [city_lat, city_lon],
            tooltip="No features match the current subcategory filters within this radius",
            icon=folium.Icon(color="gray", icon="info-sign"),
        ).add_to(m)
        return m

    active_subcats = [
        subcat for subcat in active_subcategories if subcat in county_df["subcategory"].values
    ]
    for subcat in sorted(active_subcats, key=format_subcategory_label):
        sub = county_df[county_df["subcategory"] == subcat]
        if sub.empty:
            continue
        cat = sub.iloc[0]["category"]
        cat_meta = CATEGORY_META[cat]
        icon = subcategory_div_icon(subcat, cat)
        fg = folium.FeatureGroup(name=format_subcategory_label(subcat), show=True)
        for row in sub.itertuples(index=False):
            name = row.name if pd.notna(row.name) and str(row.name).strip() else "(unnamed)"
            tip = (
                f"{name} | {cat_meta['label']} | "
                f"{format_subcategory_label(row.subcategory)} | {row.distance_km:.1f} km"
            )
            folium.Marker(
                location=[row.lat, row.lon],
                tooltip=tip,
                icon=icon,
            ).add_to(fg)
        fg.add_to(m)

    return m


@st.cache_data(show_spinner=False)
def build_category_heatmap_cached(
    county: str,
    category: str,
    county_data_json: str,
    radius_km: float,
) -> str:
    county_df = pd.read_json(io.StringIO(county_data_json))
    m = build_category_heatmap(county_df, county, category, radius_km)
    return folium_to_html(m)


def build_category_heatmap(
    county_df: pd.DataFrame,
    county: str,
    category: str,
    radius_km: float,
) -> folium.Map:
    m = _static_map_base(county, radius_km, HEATMAP_MAP_HEIGHT)
    cat_meta = CATEGORY_META[category]
    sub = county_df[county_df["category"] == category]

    if sub.empty:
        folium.Marker(
            [COUNTY_META[county]["city_lat"], COUNTY_META[county]["city_lon"]],
            tooltip=f"No {cat_meta['label']} points in buffer",
            icon=folium.Icon(color="lightgray", icon="info-sign"),
        ).add_to(m)
        return m

    heat_data = [[row.lat, row.lon] for row in sub.itertuples(index=False)]
    gradient = {
        0.2: "#ffffcc",
        0.4: cat_meta["color"],
        0.7: cat_meta["color"],
        1.0: "#1e293b",
    }
    HeatMap(
        heat_data,
        radius=18,
        blur=14,
        gradient=gradient,
    ).add_to(m)
    return m


def render_folium_html_embed(map_html: str, height: int) -> None:
    """Embed folium HTML directly (loads reliably inside inactive Streamlit tabs)."""
    st.markdown('<div class="map-frame">', unsafe_allow_html=True)
    components.html(map_html, height=height, scrolling=False)
    st.markdown("</div>", unsafe_allow_html=True)


def render_map_download(map_html: str, label: str, filename: str, key: str) -> None:
    st.download_button(
        label,
        data=map_html,
        file_name=filename,
        mime="text/html",
        key=key,
    )


def folium_to_html(m: folium.Map) -> str:
    return m.get_root().render()


def build_donut(
    series: pd.Series,
    title: str,
    label_map: dict[str, str] | None = None,
    color_map: dict[str, str] | None = None,
) -> go.Figure:
    layout_title = {"text": title, "x": 0.5, "xanchor": "center", "y": 0.98, "yanchor": "top"}
    layout_margin = {"l": 10, "r": 10, "t": CHART_TITLE_TOP_MARGIN, "b": 10}

    if series.empty:
        fig = go.Figure()
        fig.update_layout(
            title=layout_title,
            height=340,
            margin=layout_margin,
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#FFFFFF",
        )
        fig.add_annotation(text="No data", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    counts = series.value_counts()
    if isinstance(counts.index, pd.CategoricalIndex):
        counts = counts.reindex([c for c in counts.index.categories if c in counts.index and counts[c] > 0])

    labels = [label_map.get(i, str(i)) if label_map else str(i) for i in counts.index]
    colors = [color_map.get(i, "#999999") for i in counts.index] if color_map else None

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=counts.values,
                hole=0.55,
                marker={"colors": colors} if colors else None,
                textinfo="percent+label",
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title=layout_title,
        height=340,
        margin=layout_margin,
        showlegend=False,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )
    return fig


def compute_access_summary(df: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    area = buffer_area_km2(radius_km)
    rows = []
    for county in ["dublin", "galway"]:
        sub = df[df["county"] == county]
        food = sub[sub["category"].isin(FOOD_ACCESS_CATEGORIES)]

        healthy = int((food["access_tier"] == "healthy").sum())
        unhealthy = int((food["access_tier"] == "unhealthy").sum())
        mixed = int((food["access_tier"] == "mixed").sum())
        total_food = healthy + unhealthy + mixed

        rows.append(
            {
                "county": county,
                "county_label": COUNTY_META[county]["label"],
                "healthy_points": healthy,
                "unhealthy_points": unhealthy,
                "mixed_points": mixed,
                "total_food_points": total_food,
                "healthy_share_pct": round(healthy / total_food * 100, 1) if total_food else 0,
                "unhealthy_share_pct": round(unhealthy / total_food * 100, 1) if total_food else 0,
                "healthy_unhealthy_ratio": round(healthy / unhealthy, 2) if unhealthy else None,
                "healthy_density": round(healthy / area, 2),
                "unhealthy_density": round(unhealthy / area, 2),
            }
        )
    return pd.DataFrame(rows)


def build_access_tier_donut(df: pd.DataFrame, county: str) -> go.Figure:
    food = df[(df["county"] == county) & (df["category"].isin(FOOD_ACCESS_CATEGORIES))]
    tier_order = ["healthy", "unhealthy", "mixed"]
    label_map = {k: ACCESS_TIER_META[k]["label"] for k in tier_order}
    color_map = {k: ACCESS_TIER_META[k]["color"] for k in tier_order}
    return build_donut(
        food["access_tier"],
        COUNTY_META[county]["label"],
        label_map=label_map,
        color_map=color_map,
    )


def build_access_comparison_bar(summary: pd.DataFrame) -> go.Figure:
    long = summary.melt(
        id_vars=["county_label"],
        value_vars=["healthy_points", "unhealthy_points", "mixed_points"],
        var_name="access_type",
        value_name="count",
    )
    type_labels = {
        "healthy_points": "Healthy access",
        "unhealthy_points": "Unhealthy access",
        "mixed_points": "Mixed / other",
    }
    type_colors = {
        "Healthy access": ACCESS_TIER_META["healthy"]["color"],
        "Unhealthy access": ACCESS_TIER_META["unhealthy"]["color"],
        "Mixed / other": ACCESS_TIER_META["mixed"]["color"],
    }
    long["access_label"] = long["access_type"].map(type_labels)

    fig = px.bar(
        long,
        x="county_label",
        y="count",
        color="access_label",
        barmode="group",
        color_discrete_map=type_colors,
        labels={"county_label": "Area", "count": "Food access points", "access_label": "Access type"},
        title="Healthy vs unhealthy food access points",
    )
    fig.update_layout(
        height=380,
        margin={"l": 20, "r": 20, "t": CHART_TITLE_TOP_MARGIN, "b": 20},
        title={"x": 0.5, "xanchor": "center", "y": 0.98, "yanchor": "top"},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )
    return fig


def build_access_density_bar(summary: pd.DataFrame, radius_km: float) -> go.Figure:
    long = summary.melt(
        id_vars=["county_label"],
        value_vars=["healthy_density", "unhealthy_density"],
        var_name="density_type",
        value_name="density",
    )
    type_labels = {
        "healthy_density": "Healthy access",
        "unhealthy_density": "Unhealthy access",
    }
    type_colors = {
        "Healthy access": ACCESS_TIER_META["healthy"]["color"],
        "Unhealthy access": ACCESS_TIER_META["unhealthy"]["color"],
    }
    long["density_label"] = long["density_type"].map(type_labels)

    fig = px.bar(
        long,
        x="county_label",
        y="density",
        color="density_label",
        barmode="group",
        color_discrete_map=type_colors,
        labels={
            "county_label": "Area",
            "density": "Points per km² (urban buffer)",
            "density_label": "Access type",
        },
        title=f"Food access density within {radius_km:g} km of city centre",
    )
    fig.update_layout(
        height=380,
        margin={"l": 20, "r": 20, "t": CHART_TITLE_TOP_MARGIN, "b": 20},
        title={"x": 0.5, "xanchor": "center", "y": 0.98, "yanchor": "top"},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )
    return fig


def fig_to_html(fig: go.Figure) -> str:
    return fig.to_html(include_plotlyjs="cdn", full_html=True)


def render_chart_download(fig: go.Figure, label: str, filename: str, key: str) -> None:
    st.markdown('<div class="chart-dl-spacer"></div>', unsafe_allow_html=True)
    st.download_button(
        label,
        data=fig_to_html(fig),
        file_name=filename,
        mime="text/html",
        key=key,
    )
    st.markdown('<div class="chart-block-gap"></div>', unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="Rx One Health | Food Environment Ecology",
        layout="wide",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    st.markdown(
        '<div class="dashboard-header-block">'
        '<h1 class="dashboard-title-main">Capstone project Rx One Health Field Institute</h1>'
        '<h2 class="dashboard-title-sub">Food Environment Ecology</h2>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.caption("Spatial distribution of food system infrastructure from OpenStreetMap.")
    st.markdown(
        '<p class="tab-hint">👆 Select a tab below to explore food system, heatmaps, '
        'epidemiology, or vulnerability.</p>',
        unsafe_allow_html=True,
    )

    try:
        df = load_panel()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.info("Run `python3 extract_food_environment.py` first to generate data.")
        return

    warm_heatmap_cache(df, DEFAULT_RADIUS_KM)

    tab_food, tab_heatmaps, tab_epidemiology, tab_vulnerability = st.tabs(
        [
            "📍  Food System",
            "🗺️  Heatmaps",
            "📊  Epidemiology",
            "🛡️  Vulnerability",
        ]
    )

    # ── Tab 1: food distribution (point maps, stats, charts) ──────────────
    with tab_food:
        st.subheader("Map filters")
        f1, f2, f3 = st.columns([4, 2, 1])
        with f1:
            selected_categories = st.multiselect(
                "Categories",
                options=CATEGORY_ORDER,
                default=DEFAULT_CATEGORIES,
                format_func=lambda c: CATEGORY_META[c]["label"],
                key="overview_categories",
            )
        with f2:
            radius_km = st.slider(
                "Radius from city centre (km)",
                min_value=1,
                max_value=5,
                value=DEFAULT_RADIUS_KM,
                step=1,
                key="overview_radius",
            )
        with f3:
            show_named_only = st.checkbox("Named features only", value=False, key="overview_named")

        if not selected_categories:
            st.warning("Select at least one category.")
        if selected_categories:
            radius_all = filter_by_city_radius(df, radius_km)
            filtered = filter_data(radius_all, selected_categories)
            if show_named_only:
                filtered = filtered[filtered["name"].astype(str).str.strip().astype(bool)]
    
            dublin_n = len(filtered[filtered["county"] == "dublin"])
            galway_n = len(filtered[filtered["county"] == "galway"])
            st.caption(
                f"Showing {len(filtered):,} features within {radius_km} km of each city centre "
                f"(Dublin: {dublin_n:,}, Galway: {galway_n:,})."
            )
    
            st.subheader("Spatial maps")
            st.markdown(render_map_legend_html(selected_categories), unsafe_allow_html=True)
    
            data_signature = filtered.to_json()
            categories_tuple = tuple(selected_categories)
            map_key_suffix = f"{radius_km}_{'_'.join(categories_tuple)}"
    
            map_dublin_html = build_county_folium_map_cached("dublin", data_signature, categories_tuple, radius_km)
            map_galway_html = build_county_folium_map_cached("galway", data_signature, categories_tuple, radius_km)
    
            col_left, col_right = st.columns(2, gap="large")
            with col_left:
                st.markdown(f"**{COUNTY_META['dublin']['label']}**")
                render_folium_html_embed(map_dublin_html, height=POINT_MAP_HEIGHT)
                render_map_download(
                    map_dublin_html,
                    "Download Dublin map (HTML)",
                    "dublin_food_map.html",
                    f"dl_dub_map_html_{map_key_suffix}",
                )
            with col_right:
                st.markdown(f"**{COUNTY_META['galway']['label']}**")
                render_folium_html_embed(map_galway_html, height=POINT_MAP_HEIGHT)
                render_map_download(
                    map_galway_html,
                    "Download Galway map (HTML)",
                    "galway_food_map.html",
                    f"dl_gal_map_html_{map_key_suffix}",
                )
    
            st.markdown(render_osm_subcategories_html(), unsafe_allow_html=True)

            access_summary = compute_access_summary(filtered, radius_km)

            st.subheader("Food access overview")
            st.markdown(render_stats_table_html(access_summary), unsafe_allow_html=True)
            st.markdown(render_metric_definitions_html(radius_km), unsafe_allow_html=True)

            cat_label_map = {k: CATEGORY_META[k]["label"] for k in CATEGORY_META}
            cat_color_map = {k: v["color"] for k, v in CATEGORY_META.items()}

            donut_dublin = build_donut(
                filtered.loc[filtered["county"] == "dublin", "category"],
                COUNTY_META["dublin"]["label"],
                label_map=cat_label_map,
                color_map=cat_color_map,
            )
            donut_galway = build_donut(
                filtered.loc[filtered["county"] == "galway", "category"],
                COUNTY_META["galway"]["label"],
                label_map=cat_label_map,
                color_map=cat_color_map,
            )

            st.subheader("Points by category")
            d1, d2 = st.columns(2)
            with d1:
                st.plotly_chart(donut_dublin, use_container_width=True, key="donut_dublin")
                render_chart_download(
                    donut_dublin,
                    "Download Dublin chart (HTML)",
                    "dublin_category_donut.html",
                    "dl_dub_donut",
                )
            with d2:
                st.plotly_chart(donut_galway, use_container_width=True, key="donut_galway")
                render_chart_download(
                    donut_galway,
                    "Download Galway chart (HTML)",
                    "galway_category_donut.html",
                    "dl_gal_donut",
                )

            st.subheader("Healthy vs unhealthy food access")
            access_dublin = build_access_tier_donut(filtered, "dublin")
            access_galway = build_access_tier_donut(filtered, "galway")
            bar_access = build_access_comparison_bar(access_summary)
            bar_density = build_access_density_bar(access_summary, radius_km)

            a1, a2 = st.columns(2)
            with a1:
                st.plotly_chart(access_dublin, use_container_width=True, key="access_dublin")
                render_chart_download(
                    access_dublin,
                    "Download Dublin chart (HTML)",
                    "dublin_access_donut.html",
                    "dl_dub_access",
                )
            with a2:
                st.plotly_chart(access_galway, use_container_width=True, key="access_galway")
                render_chart_download(
                    access_galway,
                    "Download Galway chart (HTML)",
                    "galway_access_donut.html",
                    "dl_gal_access",
                )

            b1, b2 = st.columns(2)
            with b1:
                st.plotly_chart(bar_access, use_container_width=True, key="bar_access")
                render_chart_download(
                    bar_access,
                    "Download comparison bar chart (HTML)",
                    "food_access_comparison.html",
                    "dl_bar_access",
                )
            with b2:
                st.plotly_chart(bar_density, use_container_width=True, key="bar_density")
                render_chart_download(
                    bar_density,
                    "Download density bar chart (HTML)",
                    "food_access_density.html",
                    "dl_bar_density",
                )

            st.subheader("Spatial maps by subcategory")
            subcat_options = subcategory_options(df)
            default_subcats = [s for s in DEFAULT_SUBCATEGORIES if s in subcat_options]
            sc1, sc2 = st.columns([4, 2])
            with sc1:
                selected_subcategories = st.multiselect(
                    "Subcategories",
                    options=subcat_options,
                    default=default_subcats or subcat_options[:3],
                    format_func=format_subcategory_label,
                    key="overview_subcategories",
                )
            with sc2:
                subcat_radius_km = st.slider(
                    "Radius from city centre (km)",
                    min_value=1,
                    max_value=5,
                    value=radius_km,
                    step=1,
                    key="subcat_radius",
                )

            if not selected_subcategories:
                st.warning("Select at least one subcategory.")
            else:
                subcat_radius_all = filter_by_city_radius(df, subcat_radius_km)
                subcat_filtered = filter_by_subcategories(subcat_radius_all, selected_subcategories)
                if show_named_only:
                    subcat_filtered = subcat_filtered[
                        subcat_filtered["name"].astype(str).str.strip().astype(bool)
                    ]

                subcat_dub_n = len(subcat_filtered[subcat_filtered["county"] == "dublin"])
                subcat_gal_n = len(subcat_filtered[subcat_filtered["county"] == "galway"])
                st.caption(
                    f"Showing {len(subcat_filtered):,} features within {subcat_radius_km} km "
                    f"of each city centre (Dublin: {subcat_dub_n:,}, Galway: {subcat_gal_n:,})."
                )
                st.markdown(
                    render_subcategory_map_legend_html(subcat_radius_all, selected_subcategories),
                    unsafe_allow_html=True,
                )

                subcat_signature = subcat_filtered.to_json()
                subcats_tuple = tuple(selected_subcategories)
                subcat_map_key_suffix = f"{subcat_radius_km}_{'_'.join(subcats_tuple)}"

                subcat_map_dublin = build_county_folium_map_subcat_cached(
                    "dublin", subcat_signature, subcats_tuple, subcat_radius_km
                )
                subcat_map_galway = build_county_folium_map_subcat_cached(
                    "galway", subcat_signature, subcats_tuple, subcat_radius_km
                )

                subcat_left, subcat_right = st.columns(2, gap="large")
                with subcat_left:
                    st.markdown(f"**{COUNTY_META['dublin']['label']}**")
                    render_folium_html_embed(subcat_map_dublin, height=POINT_MAP_HEIGHT)
                    render_map_download(
                        subcat_map_dublin,
                        "Download Dublin subcategory map (HTML)",
                        "dublin_subcategory_map.html",
                        f"dl_dub_subcat_map_{subcat_map_key_suffix}",
                    )
                with subcat_right:
                    st.markdown(f"**{COUNTY_META['galway']['label']}**")
                    render_folium_html_embed(subcat_map_galway, height=POINT_MAP_HEIGHT)
                    render_map_download(
                        subcat_map_galway,
                        "Download Galway subcategory map (HTML)",
                        "galway_subcategory_map.html",
                        f"dl_gal_subcat_map_{subcat_map_key_suffix}",
                    )

            st.subheader("Subcategory density")
            dublin_top, galway_top = compute_subcategory_density_top10(df, subcat_radius_km)
            st.markdown(
                render_subcategory_density_table_html(dublin_top, galway_top, subcat_radius_km),
                unsafe_allow_html=True,
            )

            st.subheader("Points by subcategory")
            st.caption(
                f"Static view of all subcategories within {DEFAULT_RADIUS_KM:g} km of each city centre "
                "(not affected by the filters above)."
            )
            static_radius_df = filter_by_city_radius(df, DEFAULT_RADIUS_KM)
            for cat in CATEGORY_ORDER:
                sub_d1, sub_d2 = st.columns(2)
                with sub_d1:
                    sub_donut_dublin = build_category_subcategory_donut(
                        static_radius_df, "dublin", cat
                    )
                    st.plotly_chart(
                        sub_donut_dublin,
                        use_container_width=True,
                        key=f"subcat_donut_dub_{cat}",
                    )
                    render_chart_download(
                        sub_donut_dublin,
                        f"Download Dublin {CATEGORY_META[cat]['label']} subcategory chart (HTML)",
                        f"dublin_{cat}_subcategory_donut.html",
                        f"dl_dub_subcat_{cat}",
                    )
                with sub_d2:
                    sub_donut_galway = build_category_subcategory_donut(
                        static_radius_df, "galway", cat
                    )
                    st.plotly_chart(
                        sub_donut_galway,
                        use_container_width=True,
                        key=f"subcat_donut_gal_{cat}",
                    )
                    render_chart_download(
                        sub_donut_galway,
                        f"Download Galway {CATEGORY_META[cat]['label']} subcategory chart (HTML)",
                        f"galway_{cat}_subcategory_donut.html",
                        f"dl_gal_subcat_{cat}",
                    )

            st.subheader("Data export")
            csv_buf = io.StringIO()
            filtered.to_csv(csv_buf, index=False)
            st.download_button(
                "Download filtered dataset (CSV)",
                data=csv_buf.getvalue(),
                file_name="food_environment_filtered.csv",
                mime="text/csv",
                key="dl_csv",
            )
    
            with st.expander("Browse filtered records"):
                st.dataframe(
                    filtered[
                        [
                            "county_label",
                            "category_label",
                            "access_tier_label",
                            "subcategory",
                            "name",
                            "lat",
                            "lon",
                            "admin_division",
                            "distance_km",
                            "osm_id",
                        ]
                    ].rename(
                        columns={
                            "county_label": "Area",
                            "category_label": "Category",
                            "access_tier_label": "Access tier",
                            "subcategory": "Subcategory",
                            "name": "Name",
                            "lat": "Lat",
                            "lon": "Lon",
                            "admin_division": "Admin division",
                            "distance_km": "Distance (km)",
                            "osm_id": "OSM ID",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

    # ── Tab 2: heatmaps only ──────────────────────────────────────────────
    with tab_heatmaps:
        st.subheader("Heatmap settings")
        heat_radius_km = st.slider(
            "Radius from city centre (km)",
            min_value=1,
            max_value=5,
            value=DEFAULT_RADIUS_KM,
            step=1,
            key="heat_radius",
        )

        dublin_radius_json = prepare_heatmap_county_json(df, heat_radius_km, "dublin")
        galway_radius_json = prepare_heatmap_county_json(df, heat_radius_km, "galway")
        warm_heatmap_cache(df, heat_radius_km)

        st.caption(
            f"All 7 categories within {heat_radius_km} km of each city centre. "
            "Use +/- on each map to adjust zoom."
        )

        col_dub, col_gal = st.columns(2, gap="large")
        with col_dub:
            st.markdown(f"### {COUNTY_META['dublin']['label']}")
        with col_gal:
            st.markdown(f"### {COUNTY_META['galway']['label']}")

        for cat in CATEGORY_ORDER:
            st.markdown(render_category_title_html(cat), unsafe_allow_html=True)
            hm_left, hm_right = st.columns(2, gap="large")
            with hm_left:
                hm_dub = build_category_heatmap_cached(
                    "dublin", cat, dublin_radius_json, heat_radius_km
                )
                render_folium_html_embed(hm_dub, height=HEATMAP_MAP_HEIGHT)
                render_map_download(
                    hm_dub,
                    f"Download Dublin {CATEGORY_META[cat]['label']} heatmap (HTML)",
                    f"dublin_{cat}_heatmap.html",
                    f"dl_hm_dub_{cat}_{heat_radius_km}",
                )
            with hm_right:
                hm_gal = build_category_heatmap_cached(
                    "galway", cat, galway_radius_json, heat_radius_km
                )
                render_folium_html_embed(hm_gal, height=HEATMAP_MAP_HEIGHT)
                render_map_download(
                    hm_gal,
                    f"Download Galway {CATEGORY_META[cat]['label']} heatmap (HTML)",
                    f"galway_{cat}_heatmap.html",
                    f"dl_hm_gal_{cat}_{heat_radius_km}",
                )

        st.markdown(render_osm_subcategories_html(), unsafe_allow_html=True)
        st.markdown(render_heatmap_methodology_html(), unsafe_allow_html=True)

    # ── Tab 3: epidemiology population ────────────────────────────────────
    with tab_epidemiology:
        st.subheader("Epidemiology")
        st.caption(
            "Population health and epidemiological indicators for Dublin and Galway."
        )
        st.info(
            "This section will integrate population demographics, disease burden, "
            "and epidemiological datasets for comparative analysis across counties."
        )

    # ── Tab 4: vulnerability ──────────────────────────────────────────────
    with tab_vulnerability:
        st.subheader("Vulnerability")
        st.caption(
            "Social, economic, and environmental vulnerability indicators for Dublin and Galway."
        )
        st.info(
            "This section will integrate vulnerability indices and risk factors "
            "to support food environment and health equity analysis."
        )


if __name__ == "__main__":
    main()
