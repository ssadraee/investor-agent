"""
External Data Sources — Fetches supplemental data from free public APIs.

Top-level call: fetch_external_sources() → structured dict of signals.

Implemented sources (no API key required):
  1. World Bank Open Data API  — governance + macro indicators (annual)
  2. IMF DataMapper API        — WEO economic forecasts (annual/quarterly)
  3. OECD Data API             — Composite Leading Indicators (monthly)
  4. GDELT 2.0 DOC API         — geopolitical event intensity (daily/weekly)
  5. ECB SDW API               — Euro area rates + money supply (daily/monthly)

Optional sources (require free API keys in environment variables):
  6. ACLED API  (ACLED_API_KEY + ACLED_EMAIL) — armed conflict event counts
  7. NewsAPI    (NEWS_API_KEY)                 — headline attention by topic

Note: all fetchers are independent and fail gracefully with per-source logging.
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from io import StringIO
import logging

logger = logging.getLogger(__name__)

# Hard timeout for all external HTTP calls (seconds)
_TIMEOUT = 15

# Countries tracked across all sources
# Keys: ISO-2 code used internally
# Values: API-specific codes for each source
COUNTRY_MAP = {
    "US": {"wb": "US",  "imf": "USA", "oecd": "USA", "name": "United States"},
    "DE": {"wb": "DE",  "imf": "DEU", "oecd": "DEU", "name": "Germany"},
    "JP": {"wb": "JP",  "imf": "JPN", "oecd": "JPN", "name": "Japan"},
    "CN": {"wb": "CN",  "imf": "CHN", "oecd": "CHN", "name": "China"},
    "GB": {"wb": "GB",  "imf": "GBR", "oecd": "GBR", "name": "United Kingdom"},
    "FR": {"wb": "FR",  "imf": "FRA", "oecd": "FRA", "name": "France"},
    "IT": {"wb": "IT",  "imf": "ITA", "oecd": "ITA", "name": "Italy"},
    "BR": {"wb": "BR",  "imf": "BRA", "oecd": "BRA", "name": "Brazil"},
    "IN": {"wb": "IN",  "imf": "IND", "oecd": "IND", "name": "India"},
    "MX": {"wb": "MX",  "imf": "MEX", "oecd": "MEX", "name": "Mexico"},
    "AU": {"wb": "AU",  "imf": "AUS", "oecd": "AUS", "name": "Australia"},
    "ZA": {"wb": "ZA",  "imf": "ZAF", "oecd": "ZAF", "name": "South Africa"},
}

# Reverse-lookup helpers
_WB_TO_ISO2  = {v["wb"]:   k for k, v in COUNTRY_MAP.items()}
_IMF_TO_ISO2 = {v["imf"]:  k for k, v in COUNTRY_MAP.items()}
_OECD_TO_ISO2 = {v["oecd"]: k for k, v in COUNTRY_MAP.items()}


# ---------------------------------------------------------------------------
# 1. World Bank Open Data API
# ---------------------------------------------------------------------------

def fetch_world_bank_data():
    """
    Fetch governance and macro indicators from World Bank Open Data API.
    No API key required. Returns most-recent-value per country.
    Returns: {iso2: {indicator_name: {value, year}}}
    """
    indicators = {
        "NY.GDP.MKTP.KD.ZG": "gdp_growth",            # Real GDP growth %
        "FP.CPI.TOTL.ZG":    "cpi_inflation",          # Consumer price inflation %
        "BN.CAB.XOKA.GD.ZS": "current_account_pct_gdp",  # CA balance % GDP
        "PV.EST":             "political_stability",    # WGI: -2.5 (unstable) to +2.5
        "RL.EST":             "rule_of_law",            # WGI: -2.5 to +2.5
        "GE.EST":             "govt_effectiveness",     # WGI: -2.5 to +2.5
    }
    wb_codes = ";".join(v["wb"] for v in COUNTRY_MAP.values())
    results = {}

    for ind_id, ind_name in indicators.items():
        url = (
            f"https://api.worldbank.org/v2/country/{wb_codes}"
            f"/indicator/{ind_id}?format=json&mrv=3&per_page=500"
        )
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if len(data) < 2 or not data[1]:
                continue
            for record in data[1]:
                if record.get("value") is None:
                    continue
                wb_id = record.get("country", {}).get("id", "")
                iso2 = _WB_TO_ISO2.get(wb_id)
                if not iso2:
                    continue
                results.setdefault(iso2, {})
                if ind_name not in results[iso2]:  # keep only most-recent (mrv=3 → first hit is latest)
                    results[iso2][ind_name] = {
                        "value": float(record["value"]),
                        "year":  str(record.get("date", "")),
                    }
        except Exception as e:
            logger.warning(f"World Bank {ind_id} failed: {e}")

    logger.info(f"World Bank: {len(results)} countries, {len(indicators)} indicators attempted")
    return results


# ---------------------------------------------------------------------------
# 2. IMF DataMapper API
# ---------------------------------------------------------------------------

def fetch_imf_forecasts():
    """
    Fetch economic forecasts from IMF World Economic Outlook DataMapper API.
    No API key required. Prefers current-year forecast; falls back to latest available.
    Returns: {iso2: {indicator_name: {value, year}}}
    """
    indicators = {
        "NGDP_RPCH":   "gdp_growth_forecast",       # Real GDP growth %
        "PCPIPCH":     "inflation_forecast",         # CPI inflation %
        "BCA_NGDPDP":  "current_account_pct_gdp",   # Current account % GDP
        "GGXCNL_NGDP": "fiscal_balance_pct_gdp",    # Net lending/borrowing % GDP
        "LUR":         "unemployment_rate",          # Unemployment rate %
    }
    imf_codes = "+".join(v["imf"] for v in COUNTRY_MAP.values())
    current_year = str(datetime.now().year)
    results = {}

    for ind_id, ind_name in indicators.items():
        url = f"https://www.imf.org/external/datamapper/api/v1/{ind_id}/{imf_codes}"
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if "values" not in data or ind_id not in data["values"]:
                continue
            for imf_code, year_data in data["values"][ind_id].items():
                if not year_data:
                    continue
                value = year_data.get(current_year)
                if value is None:
                    latest_year = max(year_data.keys(), default=None)
                    value = year_data.get(latest_year) if latest_year else None
                if value is None:
                    continue
                iso2 = _IMF_TO_ISO2.get(imf_code)
                if not iso2:
                    continue
                results.setdefault(iso2, {})[ind_name] = {
                    "value": float(value),
                    "year":  current_year,
                }
        except Exception as e:
            logger.warning(f"IMF {ind_id} failed: {e}")

    logger.info(f"IMF DataMapper: {len(results)} countries fetched")
    return results


# ---------------------------------------------------------------------------
# 3. OECD Composite Leading Indicators
# ---------------------------------------------------------------------------

def fetch_oecd_cli():
    """
    Fetch OECD Composite Leading Indicators (CLI) — amplitude adjusted, monthly.
    No API key required. CLI > 100 = expanding; < 100 = contracting.
    Returns: {iso2: {cli, cli_mom, above_100, trend, period}}
    """
    oecd_codes = "+".join(v["oecd"] for v in COUNTRY_MAP.values()) + "+OECD"
    start_time = (datetime.now() - timedelta(days=365)).strftime("%Y-%m")

    url = (
        f"https://stats.oecd.org/sdmx-json/data/MEI_CLI/"
        f"LOLITOAA.{oecd_codes}.M/all"
        f"?format=jsondata&startTime={start_time}"
    )
    results = {}
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        # Parse SDMX-JSON: build dimension-index lookup
        dims = data.get("structure", {}).get("dimensions", {}).get("observation", [])
        dim_idx = {d["id"]: [v["id"] for v in d["values"]] for d in dims}

        loc_pos  = next((i for i, d in enumerate(dims) if d["id"] == "LOCATION"), None)
        time_pos = next((i for i, d in enumerate(dims) if d["id"] == "TIME_PERIOD"), None)
        if loc_pos is None or time_pos is None:
            return results

        obs = data.get("dataSets", [{}])[0].get("observations", {})

        # Collect all (location, time, value) tuples
        by_country = {}
        for key, vals in obs.items():
            parts = key.split(":")
            if len(parts) <= max(loc_pos, time_pos):
                continue
            if not vals or vals[0] is None:
                continue
            loc  = dim_idx["LOCATION"][int(parts[loc_pos])]
            period = dim_idx["TIME_PERIOD"][int(parts[time_pos])]
            by_country.setdefault(loc, {})[period] = float(vals[0])

        for oecd_code, ts in by_country.items():
            periods = sorted(ts)
            if not periods:
                continue
            latest = ts[periods[-1]]
            prev   = ts[periods[-2]] if len(periods) >= 2 else None
            prev3  = ts[periods[-4]] if len(periods) >= 4 else None  # 3-month trend

            iso2 = _OECD_TO_ISO2.get(oecd_code, oecd_code)
            results[iso2] = {
                "cli":       latest,
                "cli_mom":   float(latest - prev) if prev is not None else None,
                "above_100": latest > 100.0,
                "trend_3m":  float(latest - prev3) if prev3 is not None else None,
                "period":    periods[-1],
            }

        logger.info(f"OECD CLI: {len(results)} countries fetched")
    except Exception as e:
        logger.warning(f"OECD CLI fetch failed: {e}")

    return results


# ---------------------------------------------------------------------------
# 4. GDELT 2.0 DOC API — geopolitical event intensity
# ---------------------------------------------------------------------------

def fetch_gdelt_conflict():
    """
    Measure geopolitical conflict intensity via GDELT 2.0 Timeline Volume API.
    No API key required. Compares last-7-day article volume to 30-day baseline.
    Returns: {topic_key: {recent_avg, baseline_avg, intensity_ratio, elevated}}
    """
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(days=30)

    def _fmt(dt):
        return dt.strftime("%Y%m%d%H%M%S")

    # Each query targets a distinct geopolitical risk theme
    queries = {
        "middle_east_conflict":  (
            "war conflict military sanctions sourcelang:english "
            "(Israel OR Iran OR Gaza OR Lebanon OR Syria OR Yemen OR Houthi)"
        ),
        "russia_ukraine":        (
            "war conflict military sourcelang:english (Russia OR Ukraine OR NATO OR Zelensky OR Putin)"
        ),
        "china_taiwan":          (
            "military tension conflict sourcelang:english (China OR Taiwan OR PLA OR strait OR Xi)"
        ),
        "em_political_unrest":   (
            "protest coup unrest political crisis sourcelang:english "
            "(Brazil OR India OR Mexico OR Pakistan OR Turkey OR Argentina OR South Africa)"
        ),
        "trade_war_sanctions":   (
            "tariffs sanctions trade war export controls sourcelang:english"
        ),
        "north_korea_nuclear":   (
            "North Korea nuclear missile Kim Jong sourcelang:english"
        ),
    }

    results = {}
    for name, query in queries.items():
        try:
            params = {
                "query":          query,
                "mode":           "timelinevolinfo",
                "format":         "json",
                "startdatetime":  _fmt(start_dt),
                "enddatetime":    _fmt(end_dt),
                "smoothing":      3,
            }
            resp = requests.get(base_url, params=params, timeout=_TIMEOUT)
            if resp.status_code != 200:
                continue
            data = resp.json()
            timeline = data.get("timeline", [])
            if not timeline:
                continue
            series = timeline[0].get("data", [])
            values = [d["value"] for d in series if d.get("value") is not None]
            if len(values) < 7:
                continue

            recent_avg   = float(np.mean(values[-7:]))
            baseline_avg = float(np.mean(values))
            intensity    = recent_avg / baseline_avg if baseline_avg > 0 else 1.0

            results[name] = {
                "recent_avg":      recent_avg,
                "baseline_avg":    baseline_avg,
                "intensity_ratio": float(intensity),
                "elevated":        bool(intensity > 1.3),   # 30 % above baseline
                "spike":           bool(intensity > 2.0),   # 2× baseline = acute spike
            }
        except Exception as e:
            logger.warning(f"GDELT {name} failed: {e}")

    if results:
        # Aggregate: fraction of topics currently elevated
        elevated_count = sum(1 for r in results.values() if r["elevated"])
        results["_summary"] = {
            "topics_elevated":       elevated_count,
            "topics_total":          len(results) - 1,  # exclude self
            "global_tension_score":  float(
                np.mean([r["intensity_ratio"] for k, r in results.items() if k != "_summary"])
            ),
        }

    logger.info(f"GDELT: {len(results)} topics fetched")
    return results


# ---------------------------------------------------------------------------
# 5. ECB Statistical Data Warehouse
# ---------------------------------------------------------------------------

def fetch_ecb_indicators():
    """
    Fetch Euro area specific policy rates and money supply from ECB SDW.
    No API key required. Requests CSV format for easy parsing.
    Returns: {indicator_name: {latest, change, date}}
    """
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    # (display_name, SDW flow/key)
    ecb_series = [
        ("main_refinancing_rate",  "FM/B.U2.EUR.4F.KR.MRR_FR.LEV"),
        ("deposit_facility_rate",  "FM/B.U2.EUR.4F.KR.DFR.LEV"),
        ("marginal_lending_rate",  "FM/B.U2.EUR.4F.KR.MLFR.LEV"),
        ("m3_growth_yoy",          "BSI/M.U2.Y.V.M30.A.I.U2.2300.Z01.E"),
    ]

    results = {}
    for name, series_key in ecb_series:
        url = (
            f"https://data-api.ecb.europa.eu/service/data/{series_key}"
            f"?format=csvdata&startPeriod={one_year_ago}"
        )
        try:
            resp = requests.get(url, timeout=_TIMEOUT, headers={"Accept": "text/csv"})
            if resp.status_code != 200:
                continue
            df = pd.read_csv(StringIO(resp.text))
            # ECB CSV columns include TIME_PERIOD and OBS_VALUE
            val_col  = next((c for c in df.columns if "OBS_VALUE"  in c.upper()), None)
            time_col = next((c for c in df.columns if "TIME_PERIOD" in c.upper()), None)
            if val_col is None or time_col is None:
                continue
            df = df.dropna(subset=[val_col]).sort_values(time_col)
            if df.empty:
                continue
            latest = float(df[val_col].iloc[-1])
            prev   = float(df[val_col].iloc[-2]) if len(df) >= 2 else None
            results[name] = {
                "latest": latest,
                "change": float(latest - prev) if prev is not None else 0.0,
                "date":   str(df[time_col].iloc[-1]),
            }
        except Exception as e:
            logger.warning(f"ECB {name} failed: {e}")

    logger.info(f"ECB SDW: {len(results)} indicators fetched")
    return results


# ---------------------------------------------------------------------------
# 6. ACLED — Armed Conflict and Political Violence (optional, requires key)
# ---------------------------------------------------------------------------

def fetch_acled_events():
    """
    Fetch armed conflict event counts from ACLED API.
    Requires ACLED_API_KEY and ACLED_EMAIL environment variables.
    Returns: {region: {event_count, fatalities, battle_count, protest_count}}
    """
    from agent.config import ACLED_API_KEY, ACLED_EMAIL
    if not ACLED_API_KEY or not ACLED_EMAIL:
        return {}

    # Region groupings by ACLED ISO codes
    region_countries = {
        "middle_east":    ["ISR", "IRN", "IRQ", "SYR", "YEM", "LBN", "PSE"],
        "eastern_europe": ["UKR", "RUS", "BLR", "MDA", "SRB"],
        "south_asia":     ["IND", "PAK", "AFG", "BGD"],
        "east_asia":      ["CHN", "TWN", "MYS", "PHL", "MMR"],
        "sub_saharan_africa": ["SDN", "ETH", "COD", "MLI", "NER", "MOZ"],
        "latin_america":  ["COL", "MEX", "VEN", "HTI", "BRA"],
    }
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    results = {}
    for region, iso3_list in region_countries.items():
        try:
            params = {
                "key":              ACLED_API_KEY,
                "email":            ACLED_EMAIL,
                "iso":              "|".join(iso3_list),
                "event_date":       start_date,
                "event_date_where": ">=",
                "fields":           "event_type|fatalities",
                "limit":            5000,
            }
            resp = requests.get("https://api.acleddata.com/acled/read",
                                params=params, timeout=_TIMEOUT)
            data = resp.json()
            if "data" not in data or not data["data"]:
                continue
            df = pd.DataFrame(data["data"])
            df["fatalities"] = pd.to_numeric(df["fatalities"], errors="coerce").fillna(0)
            results[region] = {
                "event_count":   len(df),
                "fatalities":    int(df["fatalities"].sum()),
                "battle_count":  int((df["event_type"] == "Battles").sum()),
                "protest_count": int(df["event_type"].str.contains("Protest", na=False).sum()),
            }
        except Exception as e:
            logger.warning(f"ACLED {region} failed: {e}")

    logger.info(f"ACLED: {len(results)} regions fetched")
    return results


# ---------------------------------------------------------------------------
# 7. NewsAPI — Headline attention by topic (optional, requires key)
# ---------------------------------------------------------------------------

def fetch_news_sentiment():
    """
    Measure headline attention for geopolitical topics using NewsAPI.
    Requires NEWS_API_KEY environment variable.
    Returns: {topic: {article_count_7d, article_count_prev_7d, attention_ratio}}
    """
    from agent.config import NEWS_API_KEY
    if not NEWS_API_KEY:
        return {}

    topics = {
        "geopolitical_risk":  "war OR conflict OR military OR sanctions OR geopolitical",
        "economic_crisis":    "recession OR inflation spike OR debt crisis OR financial crisis",
        "trade_war":          "tariffs OR trade war OR trade dispute OR export controls",
        "energy_crisis":      "energy crisis OR oil shock OR gas shortage OR power outage",
        "political_instability": "coup OR political crisis OR election fraud OR protest crackdown",
    }

    def _count(query, from_date):
        params = {
            "q":        query,
            "from":     from_date.strftime("%Y-%m-%d"),
            "to":       datetime.now().strftime("%Y-%m-%d"),
            "sortBy":   "relevancy",
            "pageSize": 1,
            "language": "en",
            "apiKey":   NEWS_API_KEY,
        }
        r = requests.get("https://newsapi.org/v2/everything", params=params, timeout=_TIMEOUT)
        data = r.json()
        return data.get("totalResults", 0) if data.get("status") == "ok" else 0

    now = datetime.now()
    results = {}
    for topic, query in topics.items():
        try:
            count_recent = _count(query, now - timedelta(days=7))
            count_prev   = _count(query, now - timedelta(days=14))  # prev 7-day window
            # Normalise prev to same window size
            attention_ratio = count_recent / count_prev if count_prev > 0 else 1.0
            results[topic] = {
                "article_count_7d":      count_recent,
                "article_count_prev_7d": count_prev,
                "attention_ratio":       float(attention_ratio),
                "elevated":              bool(attention_ratio > 1.25),
            }
        except Exception as e:
            logger.warning(f"NewsAPI {topic} failed: {e}")

    logger.info(f"NewsAPI: {len(results)} topics fetched")
    return results


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def fetch_external_sources():
    """
    Fetch all external data sources. Each sub-fetch is independent and
    fails silently; missing sources return empty dicts.
    Returns structured dict consumed by scan_market().
    """
    logger.info("=== EXTERNAL DATA SOURCES FETCH START ===")

    world_bank  = fetch_world_bank_data()
    imf         = fetch_imf_forecasts()
    oecd_cli    = fetch_oecd_cli()
    gdelt       = fetch_gdelt_conflict()
    ecb         = fetch_ecb_indicators()
    acled       = fetch_acled_events()      # empty dict if no key
    news        = fetch_news_sentiment()    # empty dict if no key

    result = {
        "world_bank":  world_bank,
        "imf":         imf,
        "oecd_cli":    oecd_cli,
        "gdelt":       gdelt,
        "ecb":         ecb,
    }
    if acled:
        result["acled"] = acled
    if news:
        result["news_sentiment"] = news

    sources_ok = sum(1 for v in result.values() if v)
    logger.info(f"=== EXTERNAL SOURCES DONE: {sources_ok}/{len(result)} sources returned data ===")
    return result
