#!/usr/bin/env python3
"""Scrape FSAI food alerts and geolocate establishments to Dublin or Galway county."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.fsai.ie"
ALERTS_LIST_TEMPLATE = BASE_URL + "/news-alerts/food?page={page}"
ALL_ALERTS_LIST_TEMPLATE = BASE_URL + "/news-alert/all-alerts?page={page}"
SITEMAP_URL = BASE_URL + "/googlesitemap.xml"
DEFAULT_SINCE_DATE = "2015-01-01"
FSAI_APPROVED_PREMISES_URL = (
    BASE_URL + "/enforcement-and-legislation/official-controls/mancp/approved-food-premises"
)
OAPI_HSE_URL = "https://oapi.fsai.ie/HSEApprovedEstablishments.aspx"
SFPA_ESTABLISHMENTS_URL = (
    "https://www.sfpa.ie/What-We-Do/Seafood-Safety/"
    "Registration-Approval-of-Businesses/List-of-Approved-Establishments/Approved-Establishments"
)
DAFM_PUBLICATION_URL = (
    "https://www.gov.ie/en/department-of-agriculture-food-and-the-marine/"
    "publications/dafm-approved-establishments/"
)
FSA_UK_NI_CSV_URL = "https://fsaopendata.blob.core.windows.net/opendatacatalog/APMSNIJune2026.csv"
EU_DOOR_URL = "https://webgate.ec.europa.eu/sanco/traces/output/EN/FFP_EN.htm"

REQUEST_DELAY_SEC = 1.5
MAX_RETRIES = 1
DATA_DIR = Path(__file__).parent / "data"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
        "(academic research; contact: research@example.com)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IE,en;q=0.9",
}

APPROVAL_REGEXES = [
    re.compile(r"\bIE\s*(\d{1,5})\s*EC\b", re.IGNORECASE),
    re.compile(r"\b(\d{3,5})\s*EC\b", re.IGNORECASE),
    re.compile(r"Approval\s*(?:number|no\.?)\s*:?\s*IE\s*(\d{1,5})", re.IGNORECASE),
]

HAZARD_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"listeria\s+monocytogenes", re.I), "Listeria monocytogenes"),
    (re.compile(r"\bsalmonella\b", re.I), "Salmonella"),
    (re.compile(r"\bnorovirus\b", re.I), "Norovirus"),
    (re.compile(r"\be\.?\s*coli\b", re.I), "E. coli"),
    (re.compile(r"undeclared allergen", re.I), "undeclared allergen"),
    (re.compile(r"incorrectly declared allergen", re.I), "undeclared allergen"),
    (re.compile(r"foreign body", re.I), "foreign body"),
    (re.compile(r"pesticide", re.I), "pesticide residues"),
    (re.compile(r"mycotoxin|aflatoxin", re.I), "mycotoxins"),
    (re.compile(r"glass", re.I), "foreign body"),
    (re.compile(r"metal", re.I), "foreign body"),
    (re.compile(r"melamine", re.I), "chemical contamination"),
    (re.compile(r"histamine", re.I), "histamine"),
]

DATE_FORMATS = [
    "%A, %d %B %Y",
    "%d %B %Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
]


def create_session() -> requests.Session:
    """Return a configured requests session with polite default headers."""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def polite_sleep() -> None:
    """Pause between HTTP requests to avoid overloading remote servers."""
    time.sleep(REQUEST_DELAY_SEC)


def check_robots_allowed(session: requests.Session, url: str) -> bool:
    """Return True if robots.txt permits fetching the given URL."""
    parser = RobotFileParser()
    parser.set_url(urljoin(BASE_URL, "/robots.txt"))
    try:
        response = session.get(urljoin(BASE_URL, "/robots.txt"), timeout=30)
        response.raise_for_status()
        parser.parse(response.text.splitlines())
        return parser.can_fetch(DEFAULT_HEADERS["User-Agent"], url)
    except requests.RequestException:
        return True


def fetch_html(session: requests.Session, url: str, *, label: str = "") -> BeautifulSoup | None:
    """Fetch a URL and return parsed HTML, with one retry on 429/503."""
    if not check_robots_allowed(session, url):
        print(f"  robots.txt disallows: {url}")
        return None

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=60)
            if response.status_code in {429, 503} and attempt < MAX_RETRIES:
                print(f"  HTTP {response.status_code} for {label or url}; retrying...")
                polite_sleep()
                continue
            if response.status_code == 404:
                return None
            response.raise_for_status()
            polite_sleep()
            return BeautifulSoup(response.text, "lxml")
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                polite_sleep()
    print(f"  Failed to fetch {label or url}: {last_error}")
    return None


def fetch_bytes(session: requests.Session, url: str, *, label: str = "") -> bytes | None:
    """Download binary content (CSV/XLSX) with retry logic."""
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=120)
            if response.status_code in {429, 503} and attempt < MAX_RETRIES:
                polite_sleep()
                continue
            response.raise_for_status()
            polite_sleep()
            return response.content
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                polite_sleep()
    print(f"  Failed to download {label or url}: {last_error}")
    return None


def normalize_alert_url(href: str) -> str | None:
    """Return a canonical FSAI food-alert detail URL, or None if not a food alert."""
    if not href:
        return None
    href = href.strip().replace("\u2060", "").replace("\ufeff", "")
    if href.startswith("http"):
        url = href.split("?")[0]
    elif href.startswith("/"):
        url = urljoin(BASE_URL, href.split("?")[0])
    else:
        return None
    lower = url.lower()
    if "food-alerts" not in lower or "allergen" in lower:
        return None
    return url


def extract_food_alert_links(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Extract food-alert detail links and titles from a listing page."""
    alerts: list[dict[str, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        url = normalize_alert_url(anchor["href"])
        if not url or url in seen:
            continue
        seen.add(url)
        title = anchor.get("title", "").strip()
        if not title:
            title_el = anchor.select_one(".title")
            title = title_el.get_text(strip=True) if title_el else anchor.get_text(strip=True)
        alerts.append({"list_title": title, "source_url": url})
    return alerts


def discover_alert_urls_from_sitemap(session: requests.Session) -> set[str]:
    """Load food-alert URLs from the FSAI Google sitemap."""
    print("  Discovering URLs from sitemap...")
    urls: set[str] = set()
    try:
        response = session.get(SITEMAP_URL, timeout=60)
        response.raise_for_status()
        polite_sleep()
        for match in re.findall(r"<loc>([^<]+)</loc>", response.text):
            normalized = normalize_alert_url(match)
            if normalized:
                urls.add(normalized)
    except requests.RequestException as exc:
        print(f"    Sitemap unavailable: {exc}")
    print(f"    Sitemap: {len(urls)} food-alert URLs")
    return urls


def discover_alert_urls_from_pagination(
    session: requests.Session,
    url_template: str,
    *,
    label: str,
    max_pages: int | None,
) -> set[str]:
    """Paginate a FSAI listing until empty and collect food-alert URLs."""
    urls: set[str] = set()
    page = 1
    while True:
        if max_pages is not None and page > max_pages:
            break
        url = url_template.format(page=page)
        soup = fetch_html(session, url, label=f"{label} page {page}")
        if soup is None:
            break
        page_items = extract_food_alert_links(soup)
        if not page_items:
            break
        before_count = len(urls)
        for item in page_items:
            urls.add(item["source_url"])
        # Sidebar links repeat on later pages; stop when nothing new is found.
        if len(urls) == before_count:
            break
        page += 1
    print(f"    {label}: {len(urls)} food-alert URLs")
    return urls


def discover_all_alert_urls(session: requests.Session, max_pages: int | None) -> list[dict[str, str]]:
    """Merge sitemap and paginated listings into a deduplicated alert URL list."""
    url_set = set()
    url_set.update(discover_alert_urls_from_sitemap(session))
    url_set.update(
        discover_alert_urls_from_pagination(
            session,
            ALERTS_LIST_TEMPLATE,
            label="Food alerts listing",
            max_pages=max_pages,
        )
    )
    url_set.update(
        discover_alert_urls_from_pagination(
            session,
            ALL_ALERTS_LIST_TEMPLATE,
            label="All alerts listing",
            max_pages=max_pages,
        )
    )
    print(f"  Total unique alert URLs discovered: {len(url_set)}")
    return [{"list_title": "", "source_url": url} for url in sorted(url_set)]


def parse_date_to_datetime(raw_date: str) -> datetime | None:
    """Parse alert date strings to datetime objects."""
    if not raw_date:
        return None
    cleaned = raw_date.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def filter_records_since(
    records: list[dict[str, Any]],
    since_date: date,
) -> tuple[list[dict[str, Any]], int]:
    """Keep records on/after since_date; return filtered list and excluded count."""
    kept: list[dict[str, Any]] = []
    excluded = 0
    for row in records:
        parsed = parse_date_to_datetime(str(row.get("date", "")))
        if parsed is None or parsed.date() >= since_date:
            kept.append(row)
        else:
            excluded += 1
    return kept, excluded


def parse_alert_list_page(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Extract alert links and titles from a food-alerts list page."""
    return extract_food_alert_links(soup)


def table_to_dict(soup: BeautifulSoup, table: Any) -> dict[str, str]:
    """Convert a two-column summary table into a label -> value mapping."""
    mapping: dict[str, str] = {}
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        key = cells[0].get_text(" ", strip=True).rstrip(":").lower()
        value = cells[1].get_text("\n", strip=True)
        if key and key != "alert summary":
            mapping[key] = value
    return mapping


def extract_approval_numbers_from_text(text: str) -> list[str]:
    """Find and normalise approval numbers in free text."""
    found: list[str] = []
    for pattern in APPROVAL_REGEXES:
        for match in pattern.finditer(text):
            norm = normalize_approval_number(match.group(1))
            if norm and norm not in found:
                found.append(norm)
    return found


def extract_approvals_from_tables(article: BeautifulSoup) -> list[str]:
    """Scan all tables in the alert for approval-number columns."""
    approvals: list[str] = []
    for table in article.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if any("approval" in h for h in headers):
            col_idx = next(i for i, h in enumerate(headers) if "approval" in h)
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) <= col_idx:
                    continue
                for num in extract_approval_numbers_from_text(cells[col_idx].get_text(" ", strip=True)):
                    if num not in approvals:
                        approvals.append(num)
        for row in table.find_all("tr"):
            row_text = row.get_text(" ", strip=True)
            for num in extract_approval_numbers_from_text(row_text):
                if num not in approvals:
                    approvals.append(num)
    return approvals


def parse_alert_detail(session: requests.Session, list_item: dict[str, str]) -> dict[str, Any]:
    """Scrape a single alert detail page."""
    url = list_item["source_url"]
    soup = fetch_html(session, url, label=url)
    if soup is None:
        return {
            **list_item,
            "scrape_error": "fetch_failed",
        }

    article = soup.select_one("article.wysiwyg")
    if article is None:
        return {**list_item, "scrape_error": "no_article"}

    title_el = article.find("h2")
    title = title_el.get_text(strip=True) if title_el else list_item.get("list_title", "")

    date_el = article.select_one("p.date")
    raw_date = date_el.get_text(strip=True) if date_el else ""
    parsed_date = parse_alert_date(raw_date)

    summary_table = article.find("table")
    summary = table_to_dict(soup, summary_table) if summary_table else {}

    category = summary.get("category 1", summary.get("category", ""))
    alert_id = summary.get("alert notification", "")
    product_name = summary.get("product identification", "")
    country_origin = summary.get("country of origin", "")

    hazard_raw = ""
    for paragraph in article.find_all("p"):
        strong = paragraph.find("strong")
        if strong and "nature of danger" in strong.get_text(strip=True).lower():
            hazard_raw = paragraph.get_text("\n", strip=True)
            break

    approvals = extract_approvals_from_tables(article)
    for key, value in summary.items():
        if "approval" in key:
            for num in extract_approval_numbers_from_text(value):
                if num not in approvals:
                    approvals.append(num)
    if not approvals:
        approvals = extract_approval_numbers_from_text(article.get_text("\n", strip=True))

    return {
        "alert_id": alert_id,
        "date": parsed_date,
        "date_raw": raw_date,
        "title": title,
        "category": category,
        "country_origin": country_origin,
        "hazard_raw": hazard_raw,
        "hazard_type": classify_hazard(hazard_raw or title),
        "approval_numbers_raw": "; ".join(approvals),
        "product_name": product_name,
        "source_url": url,
        "scrape_error": "",
    }


def parse_alert_date(raw_date: str) -> str:
    """Parse FSAI alert dates to ISO YYYY-MM-DD."""
    if not raw_date:
        return ""
    cleaned = raw_date.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return cleaned


def classify_hazard(text: str) -> str:
    """Map hazard free text to a short category label."""
    if not text:
        return "unspecified"
    for pattern, label in HAZARD_RULES:
        if pattern.search(text):
            return label
    snippet = re.sub(r"\s+", " ", text).strip()
    return snippet[:80] if len(snippet) > 80 else snippet


def normalize_approval_number(value: str | int | float | None) -> str | None:
    """Normalise approval numbers to a numeric string for joining."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "-"}:
        return None
    match = re.search(r"(\d{1,5})", text)
    if not match:
        return None
    return str(int(match.group(1)))


def scrape_alert_list(
    session: requests.Session,
    max_pages: int | None,
    since_date: date,
) -> list[dict[str, Any]]:
    """Step 1: discover alert URLs, scrape detail pages, filter by since_date."""
    print(f"\n=== Step 1: Scrape FSAI food alerts (since {since_date.isoformat()}) ===")
    list_items = discover_all_alert_urls(session, max_pages=max_pages)

    print(f"  Fetching {len(list_items)} alert detail pages...")
    raw_records: list[dict[str, Any]] = []
    for idx, item in enumerate(list_items, start=1):
        if idx % 25 == 0 or idx == 1:
            print(f"    Detail {idx}/{len(list_items)}")
        raw_records.append(parse_alert_detail(session, item))

    filtered, excluded = filter_records_since(raw_records, since_date)
    if excluded:
        print(f"  Excluded {excluded} alerts before {since_date.isoformat()}")

    parsed_dates = [parse_date_to_datetime(str(r.get("date", ""))) for r in filtered]
    valid_dates = [d for d in parsed_dates if d is not None]
    if valid_dates:
        print(
            f"  Date range in scrape: {min(valid_dates).date()} to {max(valid_dates).date()} "
            f"({len(filtered)} alerts)"
        )
        if min(valid_dates).date() > since_date:
            print(
                "  Note: the FSAI website no longer hosts food alerts before "
                f"{min(valid_dates).date()}. Alerts from {since_date.year}–"
                f"{min(valid_dates).year - 1} are not available on the public site."
            )

    raw_df = pd.DataFrame(filtered)
    out_path = DATA_DIR / "fsai_alerts_raw.csv"
    raw_df.to_csv(out_path, index=False)
    print(f"  Saved {len(raw_df)} raw alerts -> {out_path}")
    return filtered


def clean_alerts(
    raw_records: list[dict[str, Any]] | pd.DataFrame,
    since_date: date,
) -> pd.DataFrame:
    """Step 2: normalise approval numbers and build clean alert dataset."""
    print(f"\n=== Step 2: Clean and normalise alerts (since {since_date.isoformat()}) ===")
    raw_df = pd.DataFrame(raw_records) if not isinstance(raw_records, pd.DataFrame) else raw_records.copy()

    clean_rows: list[dict[str, Any]] = []
    for row in raw_df.to_dict(orient="records"):
        row_date = str(row.get("date", ""))
        parsed = parse_date_to_datetime(row_date)
        if parsed is not None and parsed.date() < since_date:
            continue

        approvals = extract_approval_numbers_from_text(str(row.get("approval_numbers_raw", "")))
        if not approvals and row.get("approval_numbers_raw"):
            for part in str(row["approval_numbers_raw"]).split(";"):
                norm = normalize_approval_number(part)
                if norm and norm not in approvals:
                    approvals.append(norm)

        clean_rows.append(
            {
                "alert_id": row.get("alert_id", ""),
                "date": row_date,
                "title": row.get("title", row.get("list_title", "")),
                "category": row.get("category", ""),
                "country_origin": row.get("country_origin", ""),
                "hazard_type": row.get("hazard_type", classify_hazard(str(row.get("hazard_raw", "")))),
                "approval_numbers": ", ".join(approvals),
                "product_name": row.get("product_name", ""),
                "source_url": row.get("source_url", ""),
            }
        )

    clean_df = pd.DataFrame(clean_rows)
    out_path = DATA_DIR / "fsai_alerts_clean.csv"
    clean_df.to_csv(out_path, index=False)
    with_approval = clean_df["approval_numbers"].fillna("").astype(str).str.strip().astype(bool).sum()
    print(f"  Saved {len(clean_df)} cleaned alerts ({with_approval} with approval numbers) -> {out_path}")
    return clean_df


def parse_oapi_gridview_table(table: Any) -> list[dict[str, str]]:
    """Parse an OAPI HSE Gridview table with rowspan continuation rows."""
    records: list[dict[str, str]] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        approval = normalize_approval_number(cells[0].get_text(strip=True))
        if not approval:
            continue
        name = cells[1].get_text(" ", strip=True)
        address = cells[2].get_text(", ", strip=True)
        county = cells[3].get_text(strip=True)
        records.append(
            {
                "approval_number": approval,
                "establishment_name": name,
                "address": address,
                "county": county,
                "country": "Ireland",
                "source": "oapi_hse",
            }
        )
    return records


def load_establishments_from_oapi(session: requests.Session) -> pd.DataFrame:
    """Scrape HSE approved establishments from the FSAI OAPI portal."""
    print("  Trying OAPI HSE registry...")
    soup = fetch_html(session, OAPI_HSE_URL, label="OAPI HSE")
    if soup is None:
        return pd.DataFrame()

    records: list[dict[str, str]] = []
    for table in soup.select("table.Gridview"):
        records.extend(parse_oapi_gridview_table(table))
    df = pd.DataFrame(records).drop_duplicates(subset=["approval_number"], keep="first")
    print(f"    OAPI HSE: {len(df)} establishments")
    return df


def load_establishments_from_sfpa(session: requests.Session) -> pd.DataFrame:
    """Scrape SFPA approved establishments HTML table."""
    print("  Trying SFPA registry...")
    soup = fetch_html(session, SFPA_ESTABLISHMENTS_URL, label="SFPA establishments")
    if soup is None:
        return pd.DataFrame()

    table = soup.select_one("table#table_id") or soup.select_one("table.table")
    if table is None:
        print("    SFPA: no table found")
        return pd.DataFrame()

    headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
    records: list[dict[str, str]] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        values = [cell.get_text(" ", strip=True) for cell in cells]
        row_map = dict(zip(headers, values))
        approval = normalize_approval_number(
            row_map.get("approval number") or row_map.get("approval_number") or values[0]
        )
        if not approval:
            continue
        records.append(
            {
                "approval_number": approval,
                "establishment_name": row_map.get("establishment name", row_map.get("name", values[1] if len(values) > 1 else "")),
                "address": row_map.get("address", values[2] if len(values) > 2 else ""),
                "county": row_map.get("county", values[3] if len(values) > 3 else ""),
                "country": "Ireland",
                "source": "sfpa",
            }
        )
    df = pd.DataFrame(records).drop_duplicates(subset=["approval_number"], keep="first")
    print(f"    SFPA: {len(df)} establishments")
    return df


def discover_dafm_xlsx_urls(session: requests.Session) -> list[str]:
    """Find DAFM establishment XLSX download links via gov.ie publication page."""
    soup = fetch_html(session, DAFM_PUBLICATION_URL, label="DAFM publication page")
    if soup is None:
        return []
    urls: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.endswith(".xlsx") and "assets.gov.ie" in href:
            urls.append(href)
    return urls


def load_establishments_from_dafm(session: requests.Session) -> pd.DataFrame:
    """Download and parse DAFM approved-establishment XLSX files."""
    print("  Trying DAFM XLSX registry...")
    xlsx_urls = discover_dafm_xlsx_urls(session)
    if not xlsx_urls:
        print("    DAFM: no XLSX links found")
        return pd.DataFrame()

    records: list[dict[str, str]] = []
    for url in xlsx_urls:
        content = fetch_bytes(session, url, label=Path(url).name)
        if not content:
            continue
        try:
            workbook = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
        except Exception as exc:
            print(f"    DAFM: could not read {Path(url).name}: {exc}")
            continue
        for sheet in workbook.sheet_names:
            df = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=None, engine="openpyxl")
            header_row = None
            for idx, row in df.iterrows():
                cells = [str(v).strip().lower() for v in row.tolist() if pd.notna(v)]
                if "ie no." in cells or ("name" in cells and "county" in cells):
                    header_row = idx
                    break
            if header_row is None:
                continue
            header = [str(v).strip().lower() for v in df.iloc[header_row].tolist()]
            data = df.iloc[header_row + 1 :].copy()
            data.columns = header + [f"extra_{i}" for i in range(max(0, len(data.columns) - len(header)))]
            for _, row in data.iterrows():
                approval = normalize_approval_number(row.get("ie no."))
                if not approval:
                    continue
                town = str(row.get("town", "")).strip() if pd.notna(row.get("town")) else ""
                county = str(row.get("county", "")).strip() if pd.notna(row.get("county")) else ""
                name = str(row.get("name", "")).strip() if pd.notna(row.get("name")) else ""
                address = ", ".join(part for part in [town, county] if part)
                records.append(
                    {
                        "approval_number": approval,
                        "establishment_name": name,
                        "address": address,
                        "county": county,
                        "country": "Ireland",
                        "source": f"dafm:{Path(url).name}",
                    }
                )
    result = pd.DataFrame(records).drop_duplicates(subset=["approval_number"], keep="first")
    print(f"    DAFM: {len(result)} establishments from {len(xlsx_urls)} files")
    return result


def load_establishments_from_fsai_portal(session: requests.Session) -> pd.DataFrame:
    """Try the FSAI approved-premises hub, then linked Irish registries."""
    print("  Trying FSAI approved-premises hub...")
    soup = fetch_html(session, FSAI_APPROVED_PREMISES_URL, label="FSAI approved premises")
    if soup is None:
        print("    FSAI hub unavailable")
    else:
        print("    FSAI hub reachable (linked registries scraped separately)")

    frames = [
        load_establishments_from_dafm(session),
        load_establishments_from_oapi(session),
        load_establishments_from_sfpa(session),
    ]
    combined = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if not combined.empty:
        combined = combined.drop_duplicates(subset=["approval_number"], keep="first")
    return combined


def load_establishments_from_fsa_uk(session: requests.Session) -> pd.DataFrame:
    """Fallback: FSA UK Northern Ireland approved establishments CSV."""
    print("  Trying FSA UK Northern Ireland CSV fallback...")
    content = fetch_bytes(session, FSA_UK_NI_CSV_URL, label="FSA UK NI CSV")
    if not content:
        return pd.DataFrame()

    df = pd.read_csv(io.BytesIO(content))
    col_map = {c.lower(): c for c in df.columns}
    approval_col = col_map.get("appno") or col_map.get("approval number")
    if approval_col is None:
        print("    FSA UK: approval column not found")
        return pd.DataFrame()

    records: list[dict[str, str]] = []
    name_col = col_map.get("tradingname") or col_map.get("establishmentname")
    for _, row in df.iterrows():
        approval = normalize_approval_number(row[approval_col])
        if not approval:
            continue
        town = str(row.get(col_map.get("town", ""), "")).strip()
        county = str(row.get(col_map.get("geographiclocalauthority", ""), "")).strip()
        address_parts = [
            str(row.get(col_map.get("address1", ""), "")).strip(),
            str(row.get(col_map.get("address2", ""), "")).strip(),
            str(row.get(col_map.get("address3", ""), "")).strip(),
            town,
        ]
        address = ", ".join(part for part in address_parts if part and part.lower() != "nan")
        name = str(row.get(name_col, "")).strip() if name_col else ""
        records.append(
            {
                "approval_number": approval,
                "establishment_name": name,
                "address": address,
                "county": county,
                "country": str(row.get(col_map.get("country", ""), "Northern Ireland")).strip(),
                "source": "fsa_uk_ni",
            }
        )
    result = pd.DataFrame(records).drop_duplicates(subset=["approval_number"], keep="first")
    print(f"    FSA UK NI: {len(result)} establishments")
    return result


def load_establishments_from_eu_door(session: requests.Session) -> pd.DataFrame:
    """Final fallback: attempt to parse Ireland rows from EU DOOR export page."""
    print("  Trying EU DOOR fallback...")
    soup = fetch_html(session, EU_DOOR_URL, label="EU DOOR")
    if soup is None:
        return pd.DataFrame()

    records: list[dict[str, str]] = []
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        row_text = " | ".join(cells)
        if "ireland" not in row_text.lower() and not re.search(r"\bIE\s*\d+", row_text, re.I):
            continue
        approval = None
        for cell in cells:
            extracted = extract_approval_numbers_from_text(cell)
            approval = normalize_approval_number(extracted[0] if extracted else cell)
            if approval:
                break
        if not approval:
            continue
        records.append(
            {
                "approval_number": approval,
                "establishment_name": cells[1] if len(cells) > 1 else "",
                "address": cells[2] if len(cells) > 2 else "",
                "county": cells[3] if len(cells) > 3 else "",
                "country": "Ireland",
                "source": "eu_door",
            }
        )
    result = pd.DataFrame(records).drop_duplicates(subset=["approval_number"], keep="first")
    print(f"    EU DOOR: {len(result)} establishments")
    return result


def load_establishments(session: requests.Session) -> pd.DataFrame:
    """Step 3: load approved establishments registry from available sources."""
    print("\n=== Step 3: Load approved establishments registry ===")
    combined = load_establishments_from_fsai_portal(session)
    source_used = "fsai_linked_registries" if not combined.empty else ""

    if combined.empty:
        combined = load_establishments_from_fsa_uk(session)
        source_used = "fsa_uk_ni" if not combined.empty else ""

    if combined.empty:
        combined = load_establishments_from_eu_door(session)
        source_used = "eu_door" if not combined.empty else ""

    if combined.empty:
        raise RuntimeError("Could not load establishments from any configured source.")

    combined = combined[
        ["approval_number", "establishment_name", "address", "county", "country", "source"]
    ].drop_duplicates(subset=["approval_number"], keep="first")

    out_path = DATA_DIR / "establishments.csv"
    combined.to_csv(out_path, index=False)
    print(f"  Saved {len(combined)} establishments (primary source: {source_used or 'merged'}) -> {out_path}")
    return combined


def county_flags(county: str) -> tuple[bool, bool]:
    """Return is_dublin and is_galway booleans from a county string."""
    county_lower = (county or "").lower()
    is_dublin = "dublin" in county_lower
    is_galway = "galway" in county_lower
    return is_dublin, is_galway


def geolocate_alerts(clean_df: pd.DataFrame, establishments_df: pd.DataFrame) -> pd.DataFrame:
    """Step 4: join alerts to establishments on normalised approval numbers."""
    print("\n=== Step 4: Geolocate alerts ===")
    lookup = establishments_df.set_index("approval_number", drop=False)

    rows: list[dict[str, Any]] = []
    for alert in clean_df.to_dict(orient="records"):
        numbers = [n.strip() for n in str(alert.get("approval_numbers", "")).split(",") if n.strip()]
        match = None
        for number in numbers:
            if number in lookup.index:
                match = lookup.loc[number]
                if isinstance(match, pd.DataFrame):
                    match = match.iloc[0]
                break

        county = str(match["county"]) if match is not None else ""
        is_dublin, is_galway = county_flags(county)
        rows.append(
            {
                **alert,
                "establishment_name": str(match["establishment_name"]) if match is not None else "",
                "establishment_address": str(match["address"]) if match is not None else "",
                "county": county,
                "is_dublin": is_dublin,
                "is_galway": is_galway,
                "location_known": match is not None,
            }
        )

    geolocated = pd.DataFrame(rows)
    out_path = DATA_DIR / "fsai_alerts_geolocated.csv"
    geolocated.to_csv(out_path, index=False)
    matched = int(geolocated["location_known"].sum())
    print(f"  Saved {len(geolocated)} geolocated alerts ({matched} matched) -> {out_path}")
    return geolocated


def top_hazards(df: pd.DataFrame, county_keyword: str, n: int = 5) -> list[dict[str, Any]]:
    """Return top hazard types for alerts linked to a county keyword."""
    subset = df[df["county"].str.contains(county_keyword, case=False, na=False)]
    counts = subset["hazard_type"].value_counts().head(n)
    return [{"hazard_type": idx, "count": int(val)} for idx, val in counts.items()]


def build_summary(geolocated_df: pd.DataFrame, since_date: date) -> dict[str, Any]:
    """Step 5: compute summary statistics for console and JSON export."""
    print("\n=== Step 5: Summary ===")
    total = len(geolocated_df)
    with_approval = int(geolocated_df["approval_numbers"].fillna("").astype(str).str.strip().astype(bool).sum())
    geolocated = int(geolocated_df["location_known"].sum())
    dublin = int(geolocated_df["is_dublin"].sum())
    galway = int(geolocated_df["is_galway"].sum())
    unknown = int((~geolocated_df["location_known"]).sum())

    parsed_dates = [
        parse_date_to_datetime(str(value))
        for value in geolocated_df.get("date", pd.Series(dtype=str))
    ]
    valid_dates = [d for d in parsed_dates if d is not None]
    earliest = min(valid_dates).date().isoformat() if valid_dates else None
    latest = max(valid_dates).date().isoformat() if valid_dates else None

    summary = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "since_date_filter": since_date.isoformat(),
        "earliest_alert_date": earliest,
        "latest_alert_date": latest,
        "total_alerts_scraped": total,
        "alerts_with_approval_number": with_approval,
        "alerts_successfully_geolocated": geolocated,
        "alerts_in_dublin_county": dublin,
        "alerts_in_galway_county": galway,
        "alerts_with_unknown_location": unknown,
        "top_hazards_dublin": top_hazards(geolocated_df, "Dublin"),
        "top_hazards_galway": top_hazards(geolocated_df, "Galway"),
        "coverage_note": (
            "The FSAI public website currently indexes food alerts from approximately "
            "2022 onwards. Alerts requested from 2015 may not be available online."
        ),
    }

    print(f"  Since date filter:                 {summary['since_date_filter']}")
    print(f"  Earliest alert date:               {summary['earliest_alert_date']}")
    print(f"  Latest alert date:                 {summary['latest_alert_date']}")
    print(f"  Total alerts scraped:              {summary['total_alerts_scraped']}")
    print(f"  Alerts with approval number:       {summary['alerts_with_approval_number']}")
    print(f"  Alerts successfully geolocated:    {summary['alerts_successfully_geolocated']}")
    print(f"  Alerts in Dublin county:           {summary['alerts_in_dublin_county']}")
    print(f"  Alerts in Galway county:           {summary['alerts_in_galway_county']}")
    print(f"  Alerts with unknown location:      {summary['alerts_with_unknown_location']}")
    print("  Top 5 hazard types — Dublin:")
    for item in summary["top_hazards_dublin"]:
        print(f"    - {item['hazard_type']}: {item['count']}")
    print("  Top 5 hazard types — Galway:")
    for item in summary["top_hazards_galway"]:
        print(f"    - {item['hazard_type']}: {item['count']}")

    out_path = DATA_DIR / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  Saved summary -> {out_path}")
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape FSAI food alerts and geolocate establishments to Dublin/Galway."
    )
    parser.add_argument(
        "--since",
        default=DEFAULT_SINCE_DATE,
        help="Include alerts on or after this date (YYYY-MM-DD). Default: 2015-01-01.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=None,
        help="Limit paginated listing scrape to N pages per source (default: all).",
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Reuse existing data/fsai_alerts_raw.csv and run steps 2–5 only.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the full FSAI alerts scraping and geolocation pipeline."""
    args = parse_args(argv)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        since_date = datetime.strptime(args.since, "%Y-%m-%d").date()
    except ValueError:
        print(f"Invalid --since date: {args.since!r}. Use YYYY-MM-DD.")
        return 1

    session = create_session()
    raw_path = DATA_DIR / "fsai_alerts_raw.csv"

    if args.skip_scrape:
        if not raw_path.exists():
            print(f"Missing {raw_path}; run without --skip-scrape first.")
            return 1
        print(f"Loading existing raw alerts from {raw_path}")
        raw_df = pd.read_csv(raw_path)
        raw_records, excluded = filter_records_since(raw_df.to_dict(orient="records"), since_date)
        if excluded:
            print(f"  Excluded {excluded} loaded alerts before {since_date.isoformat()}")
        raw_df = pd.DataFrame(raw_records)
        raw_df.to_csv(raw_path, index=False)
    else:
        raw_records = scrape_alert_list(session, max_pages=args.pages, since_date=since_date)

    clean_df = clean_alerts(raw_records, since_date=since_date)
    establishments_df = load_establishments(session)
    geolocated_df = geolocate_alerts(clean_df, establishments_df)
    build_summary(geolocated_df, since_date=since_date)
    print("\nPipeline complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
