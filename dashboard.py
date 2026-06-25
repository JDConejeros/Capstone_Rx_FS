#!/usr/bin/env python3
"""Comparative food environment dashboard for Dublin and Galway."""

from __future__ import annotations

import io
import math
import base64
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
IMAGE_DIR = Path(__file__).parent / "image"
UC_DAVIS_LOGO = IMAGE_DIR / "uc_davis.png"
UCD_LOGO = IMAGE_DIR / "ucd.png"
OH_TEXT_COLOR = "#4A4A4A"
OH_NAVY = "#1E3A5F"
OH_FOREST = "#2F5D3A"
OH_FONT = "Helvetica, Arial, sans-serif"

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

COUNTY_DISPLAY_ORDER = ["galway", "dublin"]
COUNTY_LABEL_ORDER = [COUNTY_META[county]["label"] for county in COUNTY_DISPLAY_ORDER]

CATEGORY_ORDER = list(CATEGORY_META.keys())
DEFAULT_CATEGORIES = ["fast_food", "local_market", "farm"]
DEFAULT_SUBCATEGORIES = ["shop=butcher", "shop=greengrocer", "landuse=farmland"]
DEFAULT_RADIUS_KM = 5
DEFAULT_ECOLOGY_CATEGORIES = ["fast_food"]
MARKER_PX = 20
MARKER_ICON_PX = 11
SUBCATEGORY_MARKER_PX = 24
SUBCATEGORY_MARKER_ICON_PX = 13
POINT_MAP_HEIGHT = 520
HEATMAP_MAP_HEIGHT = 480
NETWORK_MAP_HEIGHT = 480
NETWORK_NODE_RADIUS = 2
NETWORK_LINE_WEIGHT = 2.5
NETWORK_LINE_OPACITY = 0.42
TRAVEL_SPEED_KMH = 4.5
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

PLATFORM_DESCRIPTION = (
    "This platform integrates food environment data, foodborne disease surveillance, and food "
    "safety alerts to compare Galway and Dublin through a One Health framework. The goal is to "
    "understand how city scale, coastal ecology, and supply chain structure shape human health "
    "outcomes. It combines HPSC epidemiological data, FSAI/RASFF alerts, and urban food system "
    "indicators to surface the connections between what people eat, where food comes from, and "
    "who gets sick. Built to support the argument that food policy is health policy, and that "
    "the gap between Galway's ecological advantage and Dublin's governance capacity is the central "
    "One Health challenge for Irish cities."
)

ONE_HEALTH_DOMAINS = {
    "human": {
        "label": "HUMAN HEALTH",
        "cx": -0.92,
        "cy": 0.82,
        "color": "#C5DDB8",
        "label_color": "#3D6B45",
    },
    "environment": {
        "label": "ENVIRONMENT",
        "cx": 0.92,
        "cy": 0.82,
        "color": "#B8D4EA",
        "label_color": "#2E6B9E",
    },
    "agriculture": {
        "label": "AGRICULTURE",
        "cx": -0.92,
        "cy": -0.82,
        "color": "#F5E6A8",
        "label_color": "#8A7340",
    },
    "society": {
        "label": "SOCIETY",
        "cx": 0.92,
        "cy": -0.82,
        "color": "#D4C5E0",
        "label_color": "#6B5088",
    },
}

OH_CENTER_RADIUS = 0.78
OH_DOMAIN_LABEL_GAP = 0.34

OH_DOMAIN_RADIUS = 1.52
OH_THEME_INSET = 0.18
OH_LABEL_MAX_DISTANCE = 0.44
OH_REGION_ANCHORS: dict[tuple[str, ...], tuple[float, float]] = {
    ("human",): (-0.68, 0.58),
    ("environment",): (0.68, 0.58),
    ("agriculture",): (-0.68, -0.58),
    ("society",): (0.68, -0.58),
    ("agriculture", "human"): (-0.92, 0.0),
    ("environment", "human"): (0.0, 0.82),
    ("environment", "agriculture"): (0.0, 0.0),
    ("agriculture", "society"): (0.0, -0.82),
    ("environment", "society"): (0.92, 0.0),
    ("human", "society"): (0.0, 0.12),
}

ONE_HEALTH_THEMES = [
    {
        "id": "spatial_food",
        "label": "Spatial food sources",
        "color": "#27AE60",
        "domains": ["human", "environment"],
        "tab": "Food System",
        "coverage": "full",
        "detail": "OSM point maps of retail, markets, farms, and food service within urban buffers.",
    },
    {
        "id": "access_equity",
        "label": "Distance & access equity",
        "color": "#2980B9",
        "domains": ["human", "society"],
        "tab": "Food System",
        "coverage": "full",
        "detail": "Healthy vs unhealthy access metrics, density, and comparative Galway and Dublin tables.",
    },
    {
        "id": "food_ecology",
        "label": "Food ecology & clustering",
        "color": "#1ABC9C",
        "domains": ["environment", "human"],
        "tab": "Food ecology",
        "coverage": "full",
        "detail": "Kernel-density heatmaps of food infrastructure by category.",
    },
    {
        "id": "foodborne_burden",
        "label": "Foodborne disease burden",
        "color": "#C0392B",
        "domains": ["human", "agriculture"],
        "tab": "Burden disease",
        "coverage": "partial",
        "detail": "HPSC epidemiological indicators (integration in progress).",
    },
    {
        "id": "alert_frequency",
        "label": "Food safety alert frequency",
        "color": "#E67E22",
        "domains": ["human", "agriculture"],
        "tab": "Alert frequency",
        "coverage": "partial",
        "detail": "FSAI/RASFF alert geolocation and temporal patterns (integration in progress).",
    },
    {
        "id": "water_risk",
        "label": "Water use & risk",
        "color": "#3498DB",
        "domains": ["environment"],
        "tab": "Water risk",
        "coverage": "partial",
        "detail": "Water infrastructure from OSM; quality and coastal risk layers pending.",
    },
    {
        "id": "waste_interface",
        "label": "Waste & animal interface",
        "color": "#7F8C8D",
        "domains": ["environment", "agriculture"],
        "tab": "Waste / animal interface",
        "coverage": "partial",
        "detail": "Waste disposal and production nodes; zoonotic overlap mapping pending.",
    },
    {
        "id": "livestock_production",
        "label": "Livestock & farm production",
        "color": "#159957",
        "domains": ["agriculture"],
        "tab": "Food System",
        "coverage": "partial",
        "detail": "OSM farm and agricultural nodes within urban buffers; species mix and throughput not yet modelled.",
    },
    {
        "id": "supply_chain",
        "label": "Supply chain & city scale",
        "color": "#5B6CFF",
        "domains": ["society", "environment"],
        "tab": "Food System",
        "coverage": "partial",
        "detail": "Urban buffer comparisons proxy supply-chain exposure; establishment-level linkage pending.",
    },
    {
        "id": "climate_coastal",
        "label": "Climate & coastal ecology",
        "color": "#0E7490",
        "domains": ["environment"],
        "tab": "Food ecology",
        "coverage": "partial",
        "detail": "Spatial food patterns as ecological proxy; climate attribution not yet modelled.",
    },
    {
        "id": "fine_spatial",
        "label": "Fine spatial patterns",
        "color": "#D97706",
        "domains": ["human", "environment"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: neighbourhood-scale census small areas and micro-buffer analysis.",
    },
    {
        "id": "nutrition_direct",
        "label": "Direct nutritional status",
        "color": "#D97706",
        "domains": ["human"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: link HSE dietary surveys or biomarkers to food environment exposure.",
    },
    {
        "id": "price_affordability",
        "label": "Price & affordability",
        "color": "#D97706",
        "domains": ["society"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: integrate CSO price indices and healthy basket cost by district.",
    },
    {
        "id": "gender_access",
        "label": "Gender & social access",
        "color": "#D97706",
        "domains": ["society"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: gender-disaggregated vulnerability and care-work food access patterns.",
    },
    {
        "id": "alert_case_link",
        "label": "Alert-to-case linkage",
        "color": "#D97706",
        "domains": ["human", "agriculture"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: connect FSAI alerts to HPSC outbreak line lists in space and time.",
    },
    {
        "id": "water_quality",
        "label": "Real-time water quality",
        "color": "#D97706",
        "domains": ["environment"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: EPA bathing-water and shellfish monitoring near food production zones.",
    },
    {
        "id": "zoonotic_overlap",
        "label": "Zoonotic overlap maps",
        "color": "#D97706",
        "domains": ["agriculture", "human"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: farm to urban edge and wildlife interface layers for Galway vs Dublin.",
    },
    {
        "id": "meat_consumption",
        "label": "Meat consumption",
        "color": "#D97706",
        "domains": ["agriculture", "human"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: link household meat intake (CSO/HSE surveys) to retail and farm-source exposure.",
    },
    {
        "id": "fish_consumption",
        "label": "Fish & seafood consumption",
        "color": "#D97706",
        "domains": ["agriculture", "human"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: map seafood retail, coastal catch zones, and per-capita fish intake by district.",
    },
    {
        "id": "milk_consumption",
        "label": "Milk & dairy consumption",
        "color": "#D97706",
        "domains": ["agriculture", "human"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: connect dairy retail density and farm supply to population dairy intake patterns.",
    },
    {
        "id": "scavenger_animals",
        "label": "Scavenger animals",
        "color": "#D97706",
        "domains": ["agriculture", "environment"],
        "tab": "Waste / animal interface",
        "coverage": "gap",
        "detail": "Opportunity: gulls, rodents, and other scavengers at waste sites and food-handling zones.",
    },
    {
        "id": "poultry_eggs",
        "label": "Poultry & egg supply",
        "color": "#D97706",
        "domains": ["agriculture"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: poultry farms, egg retail, and avian influenza risk near urban food nodes.",
    },
    {
        "id": "wildlife_feral",
        "label": "Wildlife & feral animals",
        "color": "#D97706",
        "domains": ["agriculture", "environment"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: urban wildlife corridors and feral populations overlapping food production areas.",
    },
    {
        "id": "antimicrobial_animals",
        "label": "Antimicrobial use in animals",
        "color": "#D97706",
        "domains": ["agriculture", "human"],
        "tab": "What's missing?",
        "coverage": "gap",
        "detail": "Opportunity: farm-level antimicrobial stewardship data linked to foodborne resistance burden.",
    },
]

GAP_OPPORTUNITIES = [
    "Neighbourhood-scale spatial analysis beyond OSM point resolution.",
    "Direct nutritional intake and biomarker data linked to food environment exposure.",
    "Price, affordability, and healthy-basket cost comparisons by district.",
    "Gender-disaggregated and care-work-sensitive access indicators.",
    "Spatial linkage between FSAI/RASFF alerts and HPSC confirmed outbreak cases.",
    "Real-time water-quality and coastal ecology layers for food-production zones.",
    "Climate-change attribution and future-scenario modelling at city scale.",
    "Zoonotic and farm to urban interface mapping for animal and human food pathways.",
    "Animal-source food consumption pathways for meat, fish, and dairy by district.",
    "Scavenger and wildlife interfaces at waste sites and urban food-handling zones.",
    "Poultry, egg supply chains, and avian disease risk near population centres.",
    "Farm-level antimicrobial use linked to human foodborne resistance outcomes.",
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
    .dashboard-logo-row {
        display: flex;
        justify-content: flex-start;
        align-items: center;
        gap: 28px;
        flex-wrap: wrap;
        margin: 0 0 0.85rem 0;
        padding: 0;
    }
    .dashboard-logo-row img {
        max-height: 112px;
        width: auto;
        object-fit: contain;
        display: block;
        mix-blend-mode: multiply;
    }
    .oh-network-frame {
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        overflow: hidden;
        background: #FFFFFF;
        padding: 0;
        margin-bottom: 6px;
    }
    .oh-legend-grid {
        margin: 6px 0 2px 0;
    }
    .platform-description {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px 20px;
        margin: 0.75rem 0 1rem 0;
        font-size: 1.02rem;
        color: #334155;
        line-height: 1.65;
    }
    .oh-legend-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 10px 16px;
        margin: 12px 0 4px 0;
    }
    .oh-legend-item {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.88rem;
        color: #334155;
    }
    .oh-legend-swatch {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        flex-shrink: 0;
        border: 1px solid rgba(15, 23, 42, 0.12);
    }
    .oh-domain-swatch {
        width: 18px;
        height: 18px;
        border-radius: 50%;
        flex-shrink: 0;
        border: 2px solid rgba(15, 23, 42, 0.15);
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
    for county in COUNTY_DISPLAY_ORDER:
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
        rows.append({"Metric": label, "Galway": g_fmt, "Dublin": d_fmt})
    return pd.DataFrame(rows)


def render_stats_table_html(summary: pd.DataFrame) -> str:
    table_df = build_comparative_stats_table(summary)
    body_rows = []
    for _, row in table_df.iterrows():
        body_rows.append(
            f"<tr><td>{row['Metric']}</td><td>{row['Galway']}</td><td>{row['Dublin']}</td></tr>"
        )
    return (
        '<div class="stats-table-wrap">'
        '<table class="stats-table">'
        "<thead><tr><th>Metric</th><th>Galway</th><th>Dublin</th></tr></thead>"
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
                "Galway": round(gal_count / area, 2),
                "Dublin": round(dub_count / area, 2),
            }
        )
    return pd.DataFrame(rows)


def compute_subcategory_density_top10(
    df: pd.DataFrame,
    radius_km: float,
    top_n: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = compute_subcategory_density_summary(df, radius_km)
    galway_top = summary.nlargest(top_n, "Galway")[["Subcategory", "Galway"]].reset_index(drop=True)
    dublin_top = summary.nlargest(top_n, "Dublin")[["Subcategory", "Dublin"]].reset_index(drop=True)
    return galway_top, dublin_top


def render_subcategory_density_table_html(
    galway_top: pd.DataFrame,
    dublin_top: pd.DataFrame,
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
        f"<thead><tr><th>Subcategory</th><th>Galway (per km²)</th></tr></thead>"
        f"<tbody>{_rows(galway_top, 'Galway')}</tbody>"
        "</table></div>"
        '<div class="stats-table-wrap" style="flex:1;min-width:280px;">'
        '<table class="stats-table">'
        f"<thead><tr><th>Subcategory</th><th>Dublin (per km²)</th></tr></thead>"
        f"<tbody>{_rows(dublin_top, 'Dublin')}</tbody>"
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
    title = f"{COUNTY_META[county]['label']} | {CATEGORY_META[category]['label']}"
    return build_donut(
        county_df["subcategory"],
        title,
        label_map=label_map,
        color_map=None,
    )


def travel_time_minutes(distance_km: float) -> float:
    return distance_km / TRAVEL_SPEED_KMH * 60.0


def _set_county_travel_means(
    row: dict[str, object],
    sub: pd.DataFrame,
    label: str,
) -> None:
    if sub.empty:
        row[f"{label} (km)"] = None
        row[f"{label} (min)"] = None
    else:
        mean_km = float(sub["distance_km"].mean())
        row[f"{label} (km)"] = round(mean_km, 2)
        row[f"{label} (min)"] = round(travel_time_minutes(mean_km), 1)


def compute_access_tier_travel_table(df: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    radius_df = filter_by_city_radius(df, radius_km)
    food = radius_df[radius_df["category"].isin(FOOD_ACCESS_CATEGORIES)].copy()
    rows: list[dict[str, object]] = []
    tier_order = ["healthy", "unhealthy", "mixed"]
    for tier in tier_order:
        row: dict[str, object] = {"Access tier": ACCESS_TIER_META[tier]["label"]}
        for county in COUNTY_DISPLAY_ORDER:
            label = COUNTY_META[county]["label"]
            sub = food[(food["county"] == county) & (food["access_tier"] == tier)]
            _set_county_travel_means(row, sub, label)
        rows.append(row)
    return pd.DataFrame(rows)


def compute_category_travel_table(df: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    radius_df = filter_by_city_radius(df, radius_km)
    rows: list[dict[str, object]] = []
    for cat in CATEGORY_ORDER:
        row: dict[str, object] = {"Category": CATEGORY_META[cat]["label"]}
        for county in COUNTY_DISPLAY_ORDER:
            label = COUNTY_META[county]["label"]
            sub = radius_df[(radius_df["county"] == county) & (radius_df["category"] == cat)]
            _set_county_travel_means(row, sub, label)
        rows.append(row)
    return pd.DataFrame(rows)


def compute_subcategory_travel_comparison(df: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    radius_df = filter_by_city_radius(df, radius_km)
    rows: list[dict[str, object]] = []
    for subcat in subcategory_options(radius_df):
        cat = radius_df.loc[radius_df["subcategory"] == subcat, "category"].iloc[0]
        row: dict[str, object] = {
            "Subcategory": format_subcategory_label(subcat),
            "Parent category": CATEGORY_META[cat]["label"],
        }
        for county in COUNTY_DISPLAY_ORDER:
            label = COUNTY_META[county]["label"]
            sub = radius_df[
                (radius_df["county"] == county) & (radius_df["subcategory"] == subcat)
            ]
            _set_county_travel_means(row, sub, label)
        rows.append(row)
    return pd.DataFrame(rows)


def compute_subcategory_travel_extremes(
    comparison_df: pd.DataFrame,
    top_n: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    gal_km, gal_min = "Galway (km)", "Galway (min)"
    dub_km, dub_min = "Dublin (km)", "Dublin (min)"
    gal_valid = comparison_df.dropna(subset=[gal_km])
    dub_valid = comparison_df.dropna(subset=[dub_km])
    gal_close = gal_valid.nsmallest(top_n, gal_km)[["Subcategory", gal_km, gal_min]].reset_index(
        drop=True
    )
    gal_far = gal_valid.nlargest(top_n, gal_km)[["Subcategory", gal_km, gal_min]].reset_index(
        drop=True
    )
    dub_close = dub_valid.nsmallest(top_n, dub_km)[["Subcategory", dub_km, dub_min]].reset_index(
        drop=True
    )
    dub_far = dub_valid.nlargest(top_n, dub_km)[["Subcategory", dub_km, dub_min]].reset_index(
        drop=True
    )
    return gal_close, gal_far, dub_close, dub_far


def render_subcategory_travel_extremes_html(
    gal_close: pd.DataFrame,
    gal_far: pd.DataFrame,
    dub_close: pd.DataFrame,
    dub_far: pd.DataFrame,
    radius_km: float,
    top_n: int = 5,
) -> str:
    def _rows(table: pd.DataFrame, km_col: str, min_col: str) -> str:
        body = []
        for _, row in table.iterrows():
            body.append(
                f"<tr><td>{row['Subcategory']}</td>"
                f"<td>{row[km_col]:.2f}</td>"
                f"<td>{row[min_col]:.1f}</td></tr>"
            )
        return "".join(body)

    def _pair_table(
        title: str,
        gal_table: pd.DataFrame,
        dub_table: pd.DataFrame,
        gal_km: str,
        gal_min: str,
        dub_km: str,
        dub_min: str,
    ) -> str:
        return (
            f"<p><strong>{title}</strong></p>"
            '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:4px;margin-bottom:12px;">'
            '<div class="stats-table-wrap" style="flex:1;min-width:280px;">'
            f'<div class="map-legend-title">{COUNTY_META["galway"]["label"]}</div>'
            '<table class="stats-table">'
            "<thead><tr><th>Subcategory</th><th>km</th><th>min</th></tr></thead>"
            f"<tbody>{_rows(gal_table, gal_km, gal_min)}</tbody>"
            "</table></div>"
            '<div class="stats-table-wrap" style="flex:1;min-width:280px;">'
            f'<div class="map-legend-title">{COUNTY_META["dublin"]["label"]}</div>'
            '<table class="stats-table">'
            "<thead><tr><th>Subcategory</th><th>km</th><th>min</th></tr></thead>"
            f"<tbody>{_rows(dub_table, dub_km, dub_min)}</tbody>"
            "</table></div>"
            "</div>"
        )

    return (
        '<div class="metric-definitions">'
        f"<p>Top {top_n} closest and farthest OSM subcategories by mean straight-line distance "
        f"from each city centre within a <strong>{radius_km:g} km</strong> buffer.</p>"
        "</div>"
        + _pair_table(
            "Closest to city centre (top 5)",
            gal_close,
            dub_close,
            "Galway (km)",
            "Galway (min)",
            "Dublin (km)",
            "Dublin (min)",
        )
        + _pair_table(
            "Farthest from city centre (top 5)",
            gal_far,
            dub_far,
            "Galway (km)",
            "Galway (min)",
            "Dublin (km)",
            "Dublin (min)",
        )
    )


def render_travel_stats_table_html(table_df: pd.DataFrame) -> str:
    headers = list(table_df.columns)
    head_html = "".join(f"<th>{col}</th>" for col in headers)
    body_rows = []
    for _, row in table_df.iterrows():
        cells = []
        for col in headers:
            value = row[col]
            if col.endswith("(min)") and pd.isna(value):
                cells.append("<td>N/A</td>")
            elif col.endswith("(km)") and pd.isna(value):
                cells.append("<td>N/A</td>")
            elif col.endswith("(km)") and isinstance(value, float):
                cells.append(f"<td>{value:.2f}</td>")
            elif isinstance(value, float):
                cells.append(f"<td>{value:.1f}</td>")
            else:
                cells.append(f"<td>{value}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        '<div class="stats-table-wrap">'
        '<table class="stats-table">'
        f"<thead><tr>{head_html}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def render_travel_time_methodology_html(radius_km: float) -> str:
    return (
        '<div class="heatmap-math">'
        "<h4>How average travel time is estimated</h4>"
        f"<p>Mean travel time from each city centre to food features within a "
        f"<strong>{radius_km:g} km</strong> urban buffer.</p>"
        f"<p>Distance is straight-line (haversine) from the city centre to each point. "
        f"Travel time uses a walking-speed proxy of <strong>{TRAVEL_SPEED_KMH:g} km/h</strong>:</p>"
        "<p><code>time (min) = distance (km) ÷ speed (km/h) × 60</code></p>"
        "<p>Healthy vs unhealthy rows use the same access-tier classification as the Food System tab. "
        "Subcategory extremes show the five closest and five farthest subcategories per city.</p>"
        "</div>"
    )


def render_food_network_methodology_html() -> str:
    return (
        '<div class="heatmap-math">'
        "<h4>Food network layer</h4>"
        "<p>Each map shows hub-and-spoke routes from the city centre to every point in one "
        "category within the urban buffer. Lines trace potential displacement paths; small nodes "
        "mark individual OSM features. This is a schematic food-access network, not observed "
        "movement or road routing.</p>"
        "</div>"
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
<strong>blur = 14 px</strong> (Gaussian smoothing). Values are min to max normalised to a colour gradient
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
    default_cats = tuple(DEFAULT_ECOLOGY_CATEGORIES)
    for county, county_json in (("dublin", dublin_json), ("galway", galway_json)):
        build_categories_heatmap_cached(county, default_cats, county_json, radius_km)
        build_categories_network_cached(county, default_cats, county_json, radius_km)
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
    return build_categories_heatmap(county_df, county, [category], radius_km)


def build_categories_heatmap(
    county_df: pd.DataFrame,
    county: str,
    categories: list[str],
    radius_km: float,
) -> folium.Map:
    m = _static_map_base(county, radius_km, HEATMAP_MAP_HEIGHT)
    sub = county_df[county_df["category"].isin(categories)]

    if sub.empty:
        folium.Marker(
            [COUNTY_META[county]["city_lat"], COUNTY_META[county]["city_lon"]],
            tooltip="No points for the selected categories in buffer",
            icon=folium.Icon(color="lightgray", icon="info-sign"),
        ).add_to(m)
        return m

    primary_cat = categories[0]
    cat_meta = CATEGORY_META[primary_cat]
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


@st.cache_data(show_spinner=False)
def build_categories_heatmap_cached(
    county: str,
    categories: tuple[str, ...],
    county_data_json: str,
    radius_km: float,
) -> str:
    county_df = pd.read_json(io.StringIO(county_data_json))
    m = build_categories_heatmap(county_df, county, list(categories), radius_km)
    return folium_to_html(m)


def build_category_food_network_map(
    county_df: pd.DataFrame,
    county: str,
    category: str,
    radius_km: float,
) -> folium.Map:
    return build_categories_food_network_map(county_df, county, [category], radius_km)


def build_categories_food_network_map(
    county_df: pd.DataFrame,
    county: str,
    categories: list[str],
    radius_km: float,
) -> folium.Map:
    meta = COUNTY_META[county]
    city_lat, city_lon = meta["city_lat"], meta["city_lon"]
    m = _static_map_base(county, radius_km, NETWORK_MAP_HEIGHT)
    sub = county_df[county_df["category"].isin(categories)]

    if sub.empty:
        folium.Marker(
            [city_lat, city_lon],
            tooltip="No points for the selected categories in buffer",
            icon=folium.Icon(color="lightgray", icon="info-sign"),
        ).add_to(m)
        return m

    network_fg = folium.FeatureGroup(name="Food network", show=True)
    center = [city_lat, city_lon]
    for cat in categories:
        cat_meta = CATEGORY_META[cat]
        color = cat_meta["color"]
        cat_sub = sub[sub["category"] == cat]
        for row in cat_sub.itertuples(index=False):
            location = [row.lat, row.lon]
            name = row.name if pd.notna(row.name) and str(row.name).strip() else "(unnamed)"
            travel_min = travel_time_minutes(row.distance_km)
            tip = (
                f"{name} | {cat_meta['label']} | "
                f"{format_subcategory_label(row.subcategory)} | "
                f"{row.distance_km:.1f} km | ~{travel_min:.0f} min"
            )
            folium.PolyLine(
                locations=[center, location],
                color=color,
                weight=NETWORK_LINE_WEIGHT,
                opacity=NETWORK_LINE_OPACITY,
            ).add_to(network_fg)
            folium.CircleMarker(
                location=location,
                radius=NETWORK_NODE_RADIUS,
                color=color,
                weight=1,
                fill=True,
                fill_color=color,
                fill_opacity=0.9,
                tooltip=tip,
            ).add_to(network_fg)
    network_fg.add_to(m)
    return m


@st.cache_data(show_spinner="Building food network map...")
def build_categories_network_cached(
    county: str,
    categories: tuple[str, ...],
    county_data_json: str,
    radius_km: float,
) -> str:
    county_df = pd.read_json(io.StringIO(county_data_json))
    m = build_categories_food_network_map(county_df, county, list(categories), radius_km)
    return folium_to_html(m)


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
    for county in COUNTY_DISPLAY_ORDER:
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
    fig.update_xaxes(categoryorder="array", categoryarray=COUNTY_LABEL_ORDER)
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
    fig.update_xaxes(categoryorder="array", categoryarray=COUNTY_LABEL_ORDER)
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


def _theme_opacity(coverage: str, mode: str) -> float:
    if mode == "gaps":
        if coverage == "gap":
            return 1.0
        if coverage == "partial":
            return 0.45
        return 0.25
    if coverage == "gap":
        return 0.35
    if coverage == "partial":
        return 0.85
    return 1.0


def _theme_marker_size(coverage: str, mode: str) -> int:
    if mode == "gaps" and coverage == "gap":
        return 30
    return 26


def _theme_marker_opacity(coverage: str, mode: str) -> float:
    opacity = _theme_opacity(coverage, mode)
    if mode == "overview" and coverage == "gap":
        return max(opacity, 0.55)
    return opacity


def _hex_rgba(hex_color: str, alpha: float) -> str:
    value = hex_color.lstrip("#")
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return f"rgba({red},{green},{blue},{alpha})"


def _domain_region_key(domains: list[str]) -> tuple[str, ...]:
    return tuple(sorted(domains))


def _spread_theme_positions(
    anchor: tuple[float, float],
    count: int,
    spread: float = 0.34,
    aspect: float = 1.0,
) -> list[tuple[float, float]]:
    if count <= 1:
        return [anchor]
    if count == 2:
        return [
            (anchor[0] - spread * aspect * 0.5, anchor[1]),
            (anchor[0] + spread * aspect * 0.5, anchor[1]),
        ]
    positions = []
    for idx in range(count):
        angle = (2 * math.pi * idx / count) - (math.pi / 2)
        positions.append(
            (
                anchor[0] + spread * aspect * math.cos(angle),
                anchor[1] + spread * math.sin(angle),
            )
        )
    return positions


def _spread_intersection_positions(
    domain_ids: list[str],
    count: int,
) -> list[tuple[float, float]]:
    first, second = ONE_HEALTH_DOMAINS[domain_ids[0]], ONE_HEALTH_DOMAINS[domain_ids[1]]
    mid_x = (first["cx"] + second["cx"]) / 2
    mid_y = (first["cy"] + second["cy"]) / 2
    axis_x = second["cx"] - first["cx"]
    axis_y = second["cy"] - first["cy"]
    axis_len = math.hypot(axis_x, axis_y) or 1.0
    unit_x, unit_y = axis_x / axis_len, axis_y / axis_len
    perp_x, perp_y = -unit_y, unit_x
    major = min(0.58, OH_DOMAIN_RADIUS * 0.34)
    minor = min(0.78, OH_DOMAIN_RADIUS * 0.46)
    positions: list[tuple[float, float]] = []
    for idx in range(count):
        angle = (2 * math.pi * idx / count) - (math.pi / 2)
        tx = mid_x + major * math.cos(angle) * unit_x + minor * math.sin(angle) * perp_x
        ty = mid_y + major * math.cos(angle) * unit_y + minor * math.sin(angle) * perp_y
        tx, ty = _clamp_theme_position(tx, ty, domain_ids)
        positions.append((tx, ty))
    return positions


def _theme_spread_params(count: int) -> tuple[float, float]:
    if count <= 2:
        return 0.30, 1.0
    if count <= 4:
        return 0.38, 1.12
    if count <= 6:
        return 0.46, 1.24
    return 0.54, 1.42


def _theme_min_separation(theme_a: dict, theme_b: dict) -> float:
    return 0.48 + 0.0045 * (len(theme_a["label"]) + len(theme_b["label"]))


def _label_offset_for_position(textposition: str) -> tuple[float, float]:
    dist = 0.26
    offsets = {
        "top center": (0.0, dist),
        "bottom center": (0.0, -dist),
        "middle right": (dist, 0.0),
        "middle left": (-dist, 0.0),
        "top right": (dist * 0.72, dist * 0.72),
        "top left": (-dist * 0.72, dist * 0.72),
        "bottom right": (dist * 0.72, -dist * 0.72),
        "bottom left": (-dist * 0.72, -dist * 0.72),
    }
    return offsets.get(textposition, (0.0, -dist))


def _repel_theme_markers(themes: list[dict], iterations: int = 100) -> list[dict]:
    items = [{**theme} for theme in themes]
    for _ in range(iterations):
        adjusted = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                first, second = items[i], items[j]
                dx = second["x"] - first["x"]
                dy = second["y"] - first["y"]
                dist = math.hypot(dx, dy)
                needed = 0.36
                if dist >= needed or dist < 1e-9:
                    continue
                push = (needed - dist) / 2
                ux, uy = dx / dist, dy / dist
                for idx, sign in ((i, -1), (j, 1)):
                    nx = items[idx]["x"] + sign * ux * push
                    ny = items[idx]["y"] + sign * uy * push
                    nx, ny = _clamp_theme_position(nx, ny, items[idx]["domains"])
                    items[idx]["x"], items[idx]["y"] = nx, ny
                adjusted = True
        if not adjusted:
            break
    return items


def _prepare_theme_labels(themes: list[dict]) -> list[dict]:
    prepared = []
    for theme in themes:
        textposition = _theme_text_position(theme)
        offset_x, offset_y = _label_offset_for_position(textposition)
        prepared.append(
            {
                **theme,
                "textposition": textposition,
                "label_x": theme["x"] + offset_x,
                "label_y": theme["y"] + offset_y,
            }
        )
    return _repel_theme_labels(prepared)


def _tether_label_to_marker(theme: dict) -> None:
    dx = theme["label_x"] - theme["x"]
    dy = theme["label_y"] - theme["y"]
    dist = math.hypot(dx, dy)
    if dist <= OH_LABEL_MAX_DISTANCE or dist < 1e-9:
        return
    scale = OH_LABEL_MAX_DISTANCE / dist
    theme["label_x"] = theme["x"] + dx * scale
    theme["label_y"] = theme["y"] + dy * scale


def _repel_theme_labels(themes: list[dict], iterations: int = 280) -> list[dict]:
    items = [{**theme} for theme in themes]
    for _ in range(iterations):
        adjusted = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                first, second = items[i], items[j]
                dx = second["label_x"] - first["label_x"]
                dy = second["label_y"] - first["label_y"]
                dist = math.hypot(dx, dy)
                needed = _theme_min_separation(first, second) + 0.10
                if dist >= needed or dist < 1e-9:
                    continue
                push = (needed - dist) / 2
                ux, uy = dx / dist, dy / dist
                for idx, sign in ((i, -1), (j, 1)):
                    items[idx]["label_x"] += sign * ux * push
                    items[idx]["label_y"] += sign * uy * push
                    _tether_label_to_marker(items[idx])
                adjusted = True
        if not adjusted:
            break
    for item in items:
        _tether_label_to_marker(item)
    return items


def _theme_text_position(theme: dict) -> str:
    dx = theme["x"]
    dy = theme["y"] - 0.12
    angle = math.degrees(math.atan2(dy, dx))
    if -22.5 <= angle < 22.5:
        return "middle right"
    if 22.5 <= angle < 67.5:
        return "top right"
    if 67.5 <= angle < 112.5:
        return "top center"
    if 112.5 <= angle < 157.5:
        return "top left"
    if angle >= 157.5 or angle < -157.5:
        return "middle left"
    if -157.5 <= angle < -112.5:
        return "bottom left"
    if -112.5 <= angle < -67.5:
        return "bottom center"
    return "bottom right"


def _domain_label_position(domain_id: str) -> tuple[float, float]:
    cx = ONE_HEALTH_DOMAINS[domain_id]["cx"]
    cy = ONE_HEALTH_DOMAINS[domain_id]["cy"]
    gap = OH_DOMAIN_LABEL_GAP
    radius = OH_DOMAIN_RADIUS
    if cy > 0:
        return cx, cy + radius + gap
    return cx, cy - radius - gap


def _clamp_theme_position(x: float, y: float, domain_ids: list[str]) -> tuple[float, float]:
    limit = OH_DOMAIN_RADIUS - OH_THEME_INSET
    for domain_id in domain_ids:
        cx = ONE_HEALTH_DOMAINS[domain_id]["cx"]
        cy = ONE_HEALTH_DOMAINS[domain_id]["cy"]
        dx, dy = x - cx, y - cy
        dist = math.hypot(dx, dy)
        if dist > limit:
            scale = limit / dist
            x = cx + dx * scale
            y = cy + dy * scale
    return x, y


def _layout_visible_themes(mode: str) -> list[dict]:
    grouped: dict[tuple[str, ...], list[dict]] = {}
    for theme in ONE_HEALTH_THEMES:
        if _theme_opacity(theme["coverage"], mode) <= 0.05:
            continue
        key = _domain_region_key(theme["domains"])
        grouped.setdefault(key, []).append(theme)

    laid_out: list[dict] = []
    for key, themes in grouped.items():
        anchor = OH_REGION_ANCHORS.get(key)
        if anchor is None:
            cx = sum(ONE_HEALTH_DOMAINS[d]["cx"] for d in key) / len(key)
            cy = sum(ONE_HEALTH_DOMAINS[d]["cy"] for d in key) / len(key)
            anchor = (cx, cy)
        spread, aspect = _theme_spread_params(len(themes))
        if len(key) == 2:
            positions = _spread_intersection_positions(list(key), len(themes))
        else:
            positions = _spread_theme_positions(anchor, len(themes), spread=spread, aspect=aspect)
        for theme, (tx, ty) in zip(sorted(themes, key=lambda t: t["label"]), positions):
            tx, ty = _clamp_theme_position(tx, ty, theme["domains"])
            laid_out.append({**theme, "x": tx, "y": ty})
    return _prepare_theme_labels(_repel_theme_markers(laid_out))


OH_NETWORK_LAYOUT = {
    "height": 820,
    "margin": {"l": 16, "r": 16, "t": 8, "b": 16},
    "x_range": [-3.25, 3.25],
    "y_range": [-3.45, 3.35],
}


def _apply_oh_network_layout(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        height=OH_NETWORK_LAYOUT["height"],
        margin=OH_NETWORK_LAYOUT["margin"],
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        xaxis={"visible": False, "range": OH_NETWORK_LAYOUT["x_range"]},
        yaxis={
            "visible": False,
            "range": OH_NETWORK_LAYOUT["y_range"],
            "scaleanchor": "x",
            "scaleratio": 1,
        },
        dragmode="pan",
        hovermode="closest",
    )
    return fig


def build_one_health_network(mode: str = "overview") -> go.Figure:
    fig = go.Figure()
    themes = _layout_visible_themes(mode)

    fig.add_shape(
        type="circle",
        xref="x",
        yref="y",
        x0=-OH_CENTER_RADIUS,
        y0=-OH_CENTER_RADIUS,
        x1=OH_CENTER_RADIUS,
        y1=OH_CENTER_RADIUS,
        fillcolor="rgba(255,255,255,0.94)",
        line={"color": "#CBD5E1", "width": 2.5},
        layer="below",
    )

    for domain in ONE_HEALTH_DOMAINS.values():
        cx, cy = domain["cx"], domain["cy"]
        radius = OH_DOMAIN_RADIUS
        fig.add_shape(
            type="circle",
            xref="x",
            yref="y",
            x0=cx - radius,
            y0=cy - radius,
            x1=cx + radius,
            y1=cy + radius,
            fillcolor=_hex_rgba(domain["color"], 0.58),
            line={"color": _hex_rgba(domain.get("label_color", domain["color"]), 0.9), "width": 2},
            layer="below",
        )

    for theme in themes:
        opacity = _theme_opacity(theme["coverage"], mode)
        for domain_id in theme["domains"]:
            domain = ONE_HEALTH_DOMAINS[domain_id]
            dash = "dash" if theme["coverage"] == "gap" else "solid"
            width = 1.6 if theme["coverage"] == "gap" and mode == "gaps" else 1.1
            if mode == "gaps" and theme["coverage"] != "gap":
                line_color = _hex_rgba("#64748B", opacity * 0.45)
            elif theme["coverage"] == "gap":
                line_color = _hex_rgba("#D97706", 0.35 * opacity)
            else:
                line_color = _hex_rgba(domain.get("label_color", OH_FOREST), 0.22 * opacity)
            fig.add_trace(
                go.Scatter(
                    x=[theme["x"], domain["cx"]],
                    y=[theme["y"], domain["cy"]],
                    mode="lines",
                    line={"color": line_color, "width": width, "dash": dash},
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

    if themes:
        theme_opacities = [_theme_marker_opacity(t["coverage"], mode) for t in themes]
        theme_borders = [
            2.2 if t["coverage"] == "gap" and mode == "gaps" else 1.0 for t in themes
        ]
        theme_border_colors = [
            "#D97706" if t["coverage"] == "gap" else OH_FOREST for t in themes
        ]
        for theme in themes:
            label_dist = math.hypot(theme["label_x"] - theme["x"], theme["label_y"] - theme["y"])
            if label_dist > 0.18:
                fig.add_trace(
                    go.Scatter(
                        x=[theme["x"], theme["label_x"]],
                        y=[theme["y"], theme["label_y"]],
                        mode="lines",
                        line={"color": _hex_rgba(OH_FOREST, 0.14), "width": 0.8, "dash": "dot"},
                        hoverinfo="skip",
                        showlegend=False,
                    )
                )
        fig.add_trace(
            go.Scatter(
                x=[t["x"] for t in themes],
                y=[t["y"] for t in themes],
                mode="markers",
                marker={
                    "size": [_theme_marker_size(t["coverage"], mode) for t in themes],
                    "color": [t["color"] for t in themes],
                    "opacity": theme_opacities,
                    "line": {"width": theme_borders, "color": theme_border_colors},
                },
                hovertext=[
                    f"<b>{t['label']}</b><br>"
                    f"Status: {t['coverage'].title()}<br>"
                    f"Dashboard tab: {t['tab']}<br>"
                    f"{t['detail']}"
                    for t in themes
                ],
                hoverinfo="text",
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[t["label_x"] for t in themes],
                y=[t["label_y"] for t in themes],
                mode="text",
                text=[t["label"] for t in themes],
                textposition="middle center",
                textfont={"size": 9, "color": OH_FOREST, "family": OH_FONT},
                hoverinfo="skip",
                showlegend=False,
            )
        )

    fig.add_annotation(
        x=0.0,
        y=3.12,
        text="<b>WHY FOOD MATTERS IN ONE HEALTH</b>",
        showarrow=False,
        font={"size": 15, "color": OH_NAVY, "family": OH_FONT},
        xref="x",
        yref="y",
        align="center",
    )
    fig.add_annotation(
        x=0.0,
        y=2.86,
        text=(
            "<i>Healthy People • Healthy Animals • Healthy Environment • "
            "Healthy Communities</i>"
        ),
        showarrow=False,
        font={"size": 10, "color": OH_FOREST, "family": OH_FONT},
        xref="x",
        yref="y",
        align="center",
    )

    for domain_id, domain in ONE_HEALTH_DOMAINS.items():
        label_x, label_y = _domain_label_position(domain_id)
        fig.add_annotation(
            x=label_x,
            y=label_y,
            text=f"<b>{domain['label']}</b>",
            showarrow=False,
            font={
                "size": 12,
                "color": domain.get("label_color", OH_NAVY),
                "family": OH_FONT,
            },
            xref="x",
            yref="y",
            align="center",
        )

    fig.add_annotation(
        x=0.0,
        y=0.0,
        text="<b>FOOD<br>SYSTEMS</b>",
        showarrow=False,
        font={"size": 14, "color": OH_NAVY, "family": OH_FONT},
        xref="x",
        yref="y",
        align="center",
    )

    return _apply_oh_network_layout(fig)


def render_oh_network_legend(mode: str = "overview") -> str:
    if mode == "gaps":
        items = [
            ('<span class="oh-legend-swatch" style="background:#D97706;"></span>', "Data gap / opportunity"),
            ('<span class="oh-legend-swatch" style="background:#94A3B8; opacity:0.7;"></span>', "Partially covered"),
            ('<span class="oh-legend-swatch" style="background:#CBD5E1;"></span>', "Currently mapped in dashboard"),
        ]
    else:
        items = [
            ('<span class="oh-legend-swatch" style="background:#27AE60;"></span>', "Fully mapped theme"),
            ('<span class="oh-legend-swatch" style="background:#5B6CFF; opacity:0.85;"></span>', "Partially mapped theme"),
            ('<span class="oh-legend-swatch" style="background:#D97706; opacity:0.45;"></span>', "Identified gap"),
        ]
    domain_items = "".join(
        f'<div class="oh-legend-item">'
        f'<span class="oh-domain-swatch" style="background:{d["color"]};"></span>'
        f'<span>{d["label"].replace("<br>", " ").replace("&amp;", "&").title()}</span></div>'
        for d in ONE_HEALTH_DOMAINS.values()
    )
    theme_items = "".join(
        f'<div class="oh-legend-item">{sw}<span>{label}</span></div>'
        for sw, label in items
    )
    return (
        '<div class="oh-legend-grid">'
        f"{domain_items}"
        f"{theme_items}"
        "</div>"
    )


def _trim_logo_image(path: Path) -> bytes:
    try:
        from PIL import Image

        with Image.open(path) as img:
            rgba = img.convert("RGBA")
            pixels = rgba.load()
            width, height = rgba.size
            min_x, min_y = width, height
            max_x, max_y = 0, 0
            for y in range(height):
                for x in range(width):
                    red, green, blue, alpha = pixels[x, y]
                    if alpha < 12:
                        continue
                    if red > 245 and green > 245 and blue > 245:
                        continue
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
            if max_x <= min_x or max_y <= min_y:
                return path.read_bytes()
            cropped = rgba.crop((min_x, min_y, max_x + 1, max_y + 1))
            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        return path.read_bytes()


def _logo_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    payload = _trim_logo_image(path)
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_dashboard_hero_banner() -> None:
    logos = [
        (_logo_data_uri(UC_DAVIS_LOGO), "UC Davis"),
        (_logo_data_uri(UCD_LOGO), "University College Dublin"),
    ]
    logos = [(src, alt) for src, alt in logos if src]
    if not logos:
        return
    items = "".join(
        f'<img src="{src}" alt="{alt}" />' for src, alt in logos
    )
    st.markdown(
        f'<div class="dashboard-logo-row">{items}</div>',
        unsafe_allow_html=True,
    )


def render_oh_network_chart(fig: go.Figure, chart_key: str) -> None:
    st.markdown('<div class="oh-network-frame">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, key=chart_key)
    st.markdown("</div>", unsafe_allow_html=True)


def render_oh_network_section(
    mode: str,
    chart_key: str,
    subheader: str,
    caption: str,
    footer_md: str,
) -> None:
    st.subheader(subheader)
    st.caption(caption)
    network_fig = build_one_health_network(mode=mode)
    render_oh_network_chart(network_fig, chart_key=chart_key)
    render_chart_download(
        network_fig,
        "Download interactive network chart (HTML)",
        f"one_health_network_{mode}.html",
        f"dl_oh_network_{mode}",
    )
    st.markdown(render_oh_network_legend(mode=mode), unsafe_allow_html=True)
    st.markdown(footer_md)


def main() -> None:
    st.set_page_config(
        page_title="Rx One Health | One Health Food Lens",
        layout="wide",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    render_dashboard_hero_banner()

    st.markdown(
        '<div class="dashboard-header-block">'
        '<h1 class="dashboard-title-main">Capstone Project Rx One Health Field Institute</h1>'
        '<h2 class="dashboard-title-sub">One Health Food Lens: Galway &amp; Dublin</h2>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="platform-description">{PLATFORM_DESCRIPTION}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="tab-hint">👆 Select a tab to explore the One Health food system network, '
        'maps, disease burden, alerts, and data gaps for Galway and Dublin.</p>',
        unsafe_allow_html=True,
    )

    try:
        df = load_panel()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.info("Run `python3 extract_food_environment.py` first to generate data.")
        return

    warm_heatmap_cache(df, DEFAULT_RADIUS_KM)

    (
        tab_home,
        tab_food,
        tab_heatmaps,
        tab_burden,
        tab_alerts,
        tab_water,
        tab_waste,
        tab_gaps,
    ) = st.tabs(
        [
            "🏠  Home",
            "📍  Food System",
            "🗺️  Food ecology",
            "📊  Burden disease",
            "🔔  Alert frequency",
            "💧  Water risk",
            "♻️  Waste / animal interface",
            "🔍  What's missing?",
        ]
    )

    with tab_home:
        render_oh_network_section(
            mode="overview",
            chart_key="oh_network_home",
            subheader="One Health food system network",
            caption=(
                "Four pastel domains surround a central Food Systems hub, styled after the "
                "One Health food infographic. Theme nodes sit inside each domain or at shared "
                "intersections when a dashboard theme spans two areas. Hover for details."
            ),
            footer_md=(
                "**Explore the dashboard:** use **Food System** and **Food ecology** for spatial "
                "food environment data; **Burden disease** and **Alert frequency** for health "
                "surveillance; **Water risk** and **Waste / animal interface** for ecological "
                "infrastructure; **What's missing?** for data gaps and research opportunities."
            ),
        )

    # ── Tab: Food System ──────────────────────────────────────────────────
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
                f"(Galway: {galway_n:,}, Dublin: {dublin_n:,})."
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
                st.markdown(f"**{COUNTY_META['galway']['label']}**")
                render_folium_html_embed(map_galway_html, height=POINT_MAP_HEIGHT)
                render_map_download(
                    map_galway_html,
                    "Download Galway map (HTML)",
                    "galway_food_map.html",
                    f"dl_gal_map_html_{map_key_suffix}",
                )
            with col_right:
                st.markdown(f"**{COUNTY_META['dublin']['label']}**")
                render_folium_html_embed(map_dublin_html, height=POINT_MAP_HEIGHT)
                render_map_download(
                    map_dublin_html,
                    "Download Dublin map (HTML)",
                    "dublin_food_map.html",
                    f"dl_dub_map_html_{map_key_suffix}",
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
                st.plotly_chart(donut_galway, use_container_width=True, key="donut_galway")
                render_chart_download(
                    donut_galway,
                    "Download Galway chart (HTML)",
                    "galway_category_donut.html",
                    "dl_gal_donut",
                )
            with d2:
                st.plotly_chart(donut_dublin, use_container_width=True, key="donut_dublin")
                render_chart_download(
                    donut_dublin,
                    "Download Dublin chart (HTML)",
                    "dublin_category_donut.html",
                    "dl_dub_donut",
                )

            st.subheader("Healthy vs unhealthy food access")
            access_dublin = build_access_tier_donut(filtered, "dublin")
            access_galway = build_access_tier_donut(filtered, "galway")
            bar_access = build_access_comparison_bar(access_summary)
            bar_density = build_access_density_bar(access_summary, radius_km)

            a1, a2 = st.columns(2)
            with a1:
                st.plotly_chart(access_galway, use_container_width=True, key="access_galway")
                render_chart_download(
                    access_galway,
                    "Download Galway chart (HTML)",
                    "galway_access_donut.html",
                    "dl_gal_access",
                )
            with a2:
                st.plotly_chart(access_dublin, use_container_width=True, key="access_dublin")
                render_chart_download(
                    access_dublin,
                    "Download Dublin chart (HTML)",
                    "dublin_access_donut.html",
                    "dl_dub_access",
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
                    f"of each city centre (Galway: {subcat_gal_n:,}, Dublin: {subcat_dub_n:,})."
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
                    st.markdown(f"**{COUNTY_META['galway']['label']}**")
                    render_folium_html_embed(subcat_map_galway, height=POINT_MAP_HEIGHT)
                    render_map_download(
                        subcat_map_galway,
                        "Download Galway subcategory map (HTML)",
                        "galway_subcategory_map.html",
                        f"dl_gal_subcat_map_{subcat_map_key_suffix}",
                    )
                with subcat_right:
                    st.markdown(f"**{COUNTY_META['dublin']['label']}**")
                    render_folium_html_embed(subcat_map_dublin, height=POINT_MAP_HEIGHT)
                    render_map_download(
                        subcat_map_dublin,
                        "Download Dublin subcategory map (HTML)",
                        "dublin_subcategory_map.html",
                        f"dl_dub_subcat_map_{subcat_map_key_suffix}",
                    )

            st.subheader("Subcategory density")
            galway_top, dublin_top = compute_subcategory_density_top10(df, subcat_radius_km)
            st.markdown(
                render_subcategory_density_table_html(galway_top, dublin_top, subcat_radius_km),
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
                with sub_d2:
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

    # ── Tab: Food ecology ─────────────────────────────────────────────────
    with tab_heatmaps:
        st.subheader("Food ecology")
        ec_f1, ec_f2 = st.columns([4, 2])
        with ec_f1:
            ecology_categories = st.multiselect(
                "Categories",
                options=CATEGORY_ORDER,
                default=DEFAULT_ECOLOGY_CATEGORIES,
                format_func=lambda c: CATEGORY_META[c]["label"],
                key="ecology_categories",
            )
        with ec_f2:
            ecology_radius_km = st.slider(
                "Radius from city centre (km)",
                min_value=1,
                max_value=5,
                value=DEFAULT_RADIUS_KM,
                step=1,
                key="ecology_radius",
            )

        if not ecology_categories:
            st.warning("Select at least one category.")
        else:
            ecology_cat_tuple = tuple(ecology_categories)
            dublin_radius_json = prepare_heatmap_county_json(df, ecology_radius_km, "dublin")
            galway_radius_json = prepare_heatmap_county_json(df, ecology_radius_km, "galway")
            ecology_key_suffix = f"{ecology_radius_km}_{'_'.join(ecology_cat_tuple)}"

            st.subheader("Food ecology heatmaps")
            st.caption(
                f"Kernel-density map for selected categories within {ecology_radius_km} km "
                "of each city centre. Use +/- on each map to adjust zoom."
            )
            st.markdown(render_map_legend_html(ecology_categories), unsafe_allow_html=True)

            col_gal, col_dub = st.columns(2, gap="large")
            with col_gal:
                st.markdown(f"### {COUNTY_META['galway']['label']}")
                hm_gal = build_categories_heatmap_cached(
                    "galway", ecology_cat_tuple, galway_radius_json, ecology_radius_km
                )
                render_folium_html_embed(hm_gal, height=HEATMAP_MAP_HEIGHT)
                render_map_download(
                    hm_gal,
                    "Download Galway heatmap (HTML)",
                    f"galway_ecology_heatmap_{ecology_key_suffix}.html",
                    f"dl_hm_gal_ecology_{ecology_key_suffix}",
                )
            with col_dub:
                st.markdown(f"### {COUNTY_META['dublin']['label']}")
                hm_dub = build_categories_heatmap_cached(
                    "dublin", ecology_cat_tuple, dublin_radius_json, ecology_radius_km
                )
                render_folium_html_embed(hm_dub, height=HEATMAP_MAP_HEIGHT)
                render_map_download(
                    hm_dub,
                    "Download Dublin heatmap (HTML)",
                    f"dublin_ecology_heatmap_{ecology_key_suffix}.html",
                    f"dl_hm_dub_ecology_{ecology_key_suffix}",
                )

            st.markdown(render_heatmap_methodology_html(), unsafe_allow_html=True)

            st.subheader("Food network maps")
            st.caption(
                f"Hub-and-spoke routes from each city centre to OSM points in the selected "
                f"categories within {ecology_radius_km} km."
            )
            st.markdown(render_food_network_methodology_html(), unsafe_allow_html=True)

            net_left, net_right = st.columns(2, gap="large")
            with net_left:
                st.markdown(f"### {COUNTY_META['galway']['label']}")
                net_gal = build_categories_network_cached(
                    "galway", ecology_cat_tuple, galway_radius_json, ecology_radius_km
                )
                render_folium_html_embed(net_gal, height=NETWORK_MAP_HEIGHT)
                render_map_download(
                    net_gal,
                    "Download Galway food network (HTML)",
                    f"galway_ecology_network_{ecology_key_suffix}.html",
                    f"dl_net_gal_ecology_{ecology_key_suffix}",
                )
            with net_right:
                st.markdown(f"### {COUNTY_META['dublin']['label']}")
                net_dub = build_categories_network_cached(
                    "dublin", ecology_cat_tuple, dublin_radius_json, ecology_radius_km
                )
                render_folium_html_embed(net_dub, height=NETWORK_MAP_HEIGHT)
                render_map_download(
                    net_dub,
                    "Download Dublin food network (HTML)",
                    f"dublin_ecology_network_{ecology_key_suffix}.html",
                    f"dl_net_dub_ecology_{ecology_key_suffix}",
                )

            st.markdown(render_osm_subcategories_html(), unsafe_allow_html=True)

            st.subheader("Average travel time from city centre")
            st.caption(
                f"Mean straight-line distance and estimated walking time within "
                f"{ecology_radius_km} km (at {TRAVEL_SPEED_KMH:g} km/h)."
            )
            st.markdown(render_travel_time_methodology_html(ecology_radius_km), unsafe_allow_html=True)

            tier_travel = compute_access_tier_travel_table(df, ecology_radius_km)
            st.markdown("**Healthy vs unhealthy access**", unsafe_allow_html=True)
            st.markdown(render_travel_stats_table_html(tier_travel), unsafe_allow_html=True)

            category_travel = compute_category_travel_table(df, ecology_radius_km)
            st.markdown("**General categories**", unsafe_allow_html=True)
            st.markdown(render_travel_stats_table_html(category_travel), unsafe_allow_html=True)

            subcat_comparison = compute_subcategory_travel_comparison(df, ecology_radius_km)
            gal_close, gal_far, dub_close, dub_far = compute_subcategory_travel_extremes(
                subcat_comparison
            )
            st.markdown("**OSM subcategories: closest vs farthest**", unsafe_allow_html=True)
            st.markdown(
                render_subcategory_travel_extremes_html(
                    gal_close,
                    gal_far,
                    dub_close,
                    dub_far,
                    ecology_radius_km,
                ),
                unsafe_allow_html=True,
            )

    # ── Tab: Burden disease ───────────────────────────────────────────────
    with tab_burden:
        st.subheader("Burden disease")
        st.caption(
            "Foodborne and enteric disease burden for Galway and Dublin from HPSC surveillance."
        )
        st.info(
            "This section will integrate HPSC epidemiological indicators, outbreak trends, "
            "and comparative disease burden across counties within the One Health framework."
        )

    # ── Tab: Alert frequency ──────────────────────────────────────────────
    with tab_alerts:
        st.subheader("Alert frequency")
        st.caption(
            "FSAI and RASFF food safety alert frequency and geolocation for Galway and Dublin."
        )
        st.info(
            "This section will integrate FSAI/RASFF alert timelines, hazard categories, "
            "and spatial patterns to link food safety signals with population exposure."
        )

    # ── Tab: Water risk ───────────────────────────────────────────────────
    with tab_water:
        st.subheader("Water risk")
        st.caption(
            "Water infrastructure, coastal ecology, and exposure risk in urban food environments."
        )
        st.info(
            "This section will combine OSM water features with EPA bathing-water quality, "
            "shellfish monitoring, and coastal risk layers for Galway and Dublin."
        )

    # ── Tab: Waste / animal interface ─────────────────────────────────────
    with tab_waste:
        st.subheader("Waste / animal interface")
        st.caption(
            "Waste disposal, primary production, and animal and human food pathway interfaces."
        )
        st.info(
            "This section will map waste infrastructure, farm to urban edges, and zoonotic "
            "interface zones to support One Health food safety analysis."
        )

    # ── Tab: What's missing? ──────────────────────────────────────────────
    with tab_gaps:
        gap_list = "".join(f"- {item}\n" for item in GAP_OPPORTUNITIES)
        render_oh_network_section(
            mode="gaps",
            chart_key="oh_network_gaps",
            subheader="What's missing? opportunity windows",
            caption=(
                "The same One Health network, highlighting themes that current data cannot yet "
                "resolve and where additional evidence would strengthen food and health policy."
            ),
            footer_md=f"**Priority opportunity windows**\n{gap_list}",
        )


if __name__ == "__main__":
    main()
