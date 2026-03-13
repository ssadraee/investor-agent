"""
Autonomous Investor Agent — Configuration
All parameters, universe definitions, and constants.
"""
import os

# === CAPITAL ===
INITIAL_CAPITAL = 10_000.0  # EUR virtual capital
TRANSACTION_COST_BPS = 10   # 0.10% conservative estimate

# === INVESTMENT UNIVERSE ===
# Liquid ETFs spanning asset classes, sectors, geographies
UNIVERSE = {
    # US Broad Market (UCITS)
    "CSPX": "S&P 500",
    "EQQQ": "Nasdaq 100",
    "IEUS": "Russell 2000",
    # International (UCITS)
    "IEFA": "EAFE Developed Markets",
    "IEMG": "Emerging Markets",
    # Sectors (UCITS)
    "IXN": "Technology",
    "IXG": "Financials",
    "IXC": "Energy",
    "IXJ": "Healthcare",
    "EXH1": "Industrials",
    "IXI": "Consumer Staples",
    "JXI": "Utilities",
    # Fixed Income (UCITS)
    "EDV": "20+ Year Treasury",
    "IBTM": "7-10 Year Treasury",
    "AGGG": "US Aggregate Bond",
    "LQDE": "Investment Grade Corporate",
    # Alternatives (UCITS)
    "GLDA": "Gold",
    "IWDP": "US REITs",
    "CMOD": "Commodities Broad",
}

# === BENCHMARKS ===
BENCHMARK_TICKER = "CSPX"

# === ALLOCATION CONSTRAINTS ===
MAX_POSITION_WEIGHT = 0.40       # 40% max per asset
MIN_ASSETS = 3                    # Minimum 3 assets
MAX_CASH_WEIGHT = 0.30           # Max 30% cash (crisis only)
MIN_POSITION_WEIGHT = 0.02       # 2% minimum if included

# === RISK PARAMETERS ===
RISK_FREE_RATE = 0.045           # ~4.5% annualized (T-bill proxy)
EWMA_HALFLIFE = 21               # Days for EWMA covariance
LOOKBACK_DAYS = 252              # 1 year price history
SHORT_LOOKBACK = 63              # 3 months for momentum

# === REGIME THRESHOLDS ===
VIX_LOW = 16.0
VIX_HIGH = 25.0
VIX_CRISIS = 35.0
MOMENTUM_LOOKBACK = 63           # Days

# === REGIME RISK BUDGETS ===
REGIME_PARAMS = {
    "risk_on": {
        "equity_max": 0.85,
        "bond_min": 0.05,
        "cash_target": 0.0,
        "risk_aversion": 1.0,
    },
    "risk_off": {
        "equity_max": 0.50,
        "bond_min": 0.25,
        "cash_target": 0.10,
        "risk_aversion": 3.0,
    },
    "transition": {
        "equity_max": 0.65,
        "bond_min": 0.15,
        "cash_target": 0.05,
        "risk_aversion": 2.0,
    },
    "crisis": {
        "equity_max": 0.30,
        "bond_min": 0.30,
        "cash_target": 0.20,
        "risk_aversion": 5.0,
    },
}

# Asset class mapping
EQUITY_TICKERS = ["CSPX", "EQQQ", "IEUS", "IEFA", "IEMG", "IXN", "IXG", "IXC", "IXJ", "EXH1", "IXI", "JXI"]
BOND_TICKERS = ["EDV", "IBTM", "AGGG", "LQDE"]
ALT_TICKERS = ["GLDA", "IWDP", "CMOD"]

# === LEARNING PARAMETERS ===
LEARNING_RATE = 0.1
FORGETTING_FACTOR = 0.95
MIN_WEEKS_BEFORE_DRIFT = 8       # Weeks before weights can deviate >20%
MAX_WEIGHT_DEVIATION = 0.20      # Max deviation from prior

# === SIGNAL NAMES ===
# First 6: original US-centric market signals
# Last 6: global data sources wired in via regime.py (see classify_regime)
SIGNALS = [
    "momentum",
    "mean_reversion",
    "volatility_regime",
    "macro_trend",
    "yield_curve",
    "cross_asset_momentum",
    # High-frequency global signals (daily, from yfinance + FRED)
    "global_breadth",       # % of world equity markets rising + OECD CLI breadth
    "fx_stress",            # safe-haven demand (JPY/CHF) + EM currency pressure
    "credit_conditions",    # HY/EM credit spreads + EPU policy uncertainty
    # Lower-frequency external sources (weekly/monthly)
    "geopolitical_risk",    # GDELT conflict intensity + World Bank political stability
    "leading_indicators",   # OECD CLI momentum + IMF GDP growth forecasts
    "global_monetary",      # ECB rate direction + M3 + international yield trends
]

# === FRED SERIES (free API) ===
FRED_SERIES = {
    "DGS10": "10Y Treasury Yield",
    "DGS2": "2Y Treasury Yield",
    "DTWEXBGS": "Trade-Weighted USD",
    "UNRATE": "Unemployment Rate",
    "CPIAUCSL": "CPI All Urban",
    "GDPC1": "Real GDP",
    "FEDFUNDS": "Fed Funds Rate",
}

# === GLOBAL EQUITY INDICES (via yfinance) — signals only, not investable universe ===
REGIONAL_INDICES = {
    # Europe
    "^STOXX50E": "Euro Stoxx 50",
    "^GDAXI":    "DAX (Germany)",
    "^FTSE":     "FTSE 100 (UK)",
    "^FCHI":     "CAC 40 (France)",
    # Asia-Pacific
    "^N225":     "Nikkei 225 (Japan)",
    "^HSI":      "Hang Seng (Hong Kong)",
    "^AXJO":     "ASX 200 (Australia)",
    "^BSESN":    "BSE Sensex (India)",
    "000001.SS": "Shanghai Composite (China)",
    # Americas ex-US
    "^BVSP":     "Bovespa (Brazil)",
    "^MXX":      "IPC (Mexico)",
}

# === FX SPOT PAIRS (via yfinance) ===
# Quoted as: EURUSD=X → EUR per 1 USD unit; USDJPY=X → JPY per 1 USD; etc.
FX_TICKERS = {
    "EURUSD=X":  "EUR/USD",
    "GBPUSD=X":  "GBP/USD",
    "USDJPY=X":  "USD/JPY",
    "USDCNY=X":  "USD/CNY",
    "USDBRL=X":  "USD/BRL",
    "USDINR=X":  "USD/INR",
    "AUDUSD=X":  "AUD/USD",
    "USDCHF=X":  "USD/CHF",
}

# === COMMODITY FUTURES (via yfinance) ===
COMMODITY_TICKERS = {
    "CL=F":  "WTI Crude Oil",
    "BZ=F":  "Brent Crude",
    "NG=F":  "Natural Gas",
    "HG=F":  "Copper",
    "GC=F":  "Gold Futures",
    "ZW=F":  "Wheat",
    "SI=F":  "Silver",
}

# === GLOBAL FRED SERIES — international macro, credit spreads, policy uncertainty ===
# All fetched with graceful per-series fallback; series that are unavailable are skipped.
FRED_SERIES_GLOBAL = {
    # --- International long-term bond yields (monthly, %) ---
    "IRLTLT01EZM156N": "Euro Area 10Y Yield",
    "IRLTLT01JPM156N": "Japan 10Y Yield",
    "IRLTLT01GBM156N": "UK 10Y Yield",
    # --- FRED FX rates (daily) ---
    "DEXUSEU":  "USD per EUR",
    "DEXJPUS":  "JPY per USD",
    "DEXCHUS":  "CNY per USD",
    "DEXBZUS":  "BRL per USD",
    # --- International CPI (monthly, YoY %) ---
    "CPALTT01EZM659N":  "Euro Area HICP YoY",
    "JPNCPIALLMINMEI":  "Japan CPI YoY",
    "GBRCPIALLMINMEI":  "UK CPI YoY",
    # --- International unemployment (monthly, %) ---
    "LRHUTTTTEZM156S":  "Euro Area Unemployment",
    "LRHUTTTTJPM156S":  "Japan Unemployment",
    # --- Credit / financial stress (daily, option-adjusted spread in bp) ---
    "BAMLH0A0HYM2":     "US High Yield OAS",
    "BAMLC0A0CM":       "US Inv Grade OAS",
    "BAMLEMCBPIOAS":    "EM Corp Bond OAS",
    # --- Economic policy uncertainty (daily index, US) ---
    "USEPUINDXD":       "US Economic Policy Uncertainty",
}

# === PROPOSED ADDITIONAL FREE DATA SOURCES (not yet implemented) ===
# These sources can further enrich geopolitical and political risk signals:
#
# 1. GDELT Project (gdeltproject.org/api.html) — free, no key required.
#    Real-time global event/news database. Tone, conflict, protest, and cooperation
#    counts by country. Queryable via BigQuery (free tier) or direct API.
#
# 2. World Bank Open Data API (api.worldbank.org/v2) — free, no key required.
#    Political Stability, Rule of Law, Government Effectiveness (WGI, annual).
#    Also: GDP growth, inflation, current account balance by country.
#
# 3. IMF Data API (imf.org/external/datamapper/api/v1) — free, no key required.
#    WEO forecasts, global debt, fiscal balance, current account by country.
#
# 4. ECB Statistical Data Warehouse (data-api.ecb.europa.eu) — free, no key required.
#    Euro area: sovereign yield spreads (BTP-Bund), bank lending rates, M3 money supply.
#
# 5. OECD Data API (stats.oecd.org/sdmx-json) — free, no key required.
#    Composite Leading Indicators (CLI), consumer/business confidence by country.
#
# 6. GPR Index (matteoiacoviello.com/gpr.htm) — free CSV download (monthly).
#    Caldara & Iacoviello's Geopolitical Risk Index: global + country-level.
#    Can be cached locally and refreshed monthly via GitHub Actions.
#
# 7. Economic Policy Uncertainty — Global (policyuncertainty.com) — free CSV.
#    Country-level EPU indices for EU, China, Russia, India, Brazil, and more.
#    US daily EPU is also available via FRED (USEPUINDXD, already included above).
#
# 8. ACLED (acleddata.com) — free for non-commercial use (registration required).
#    Armed conflict and protest event data by country/date. Useful for EM risk.
#
# 9. UN Comtrade (comtradeplus.un.org) — free tier (500 calls/day).
#    Bilateral trade flows. Useful for trade-war and supply chain risk signals.
#
# 10. NewsAPI (newsapi.org) — free tier (100 req/day).
#     Headline sentiment by keyword/country. Basic geopolitical news signal.

# === PATHS ===
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "agent.db")
DOCS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
HISTORY_PATH = os.path.join(DOCS_PATH, "history")

# === EMAIL ===
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# === OPTIONAL EXTERNAL SOURCE API KEYS ===
# These keys are not required; the corresponding fetchers return {} when absent.
# Add them as GitHub Secrets and they will be injected automatically.
ACLED_API_KEY = os.environ.get("ACLED_API_KEY", "")   # acleddata.com — free registration
ACLED_EMAIL   = os.environ.get("ACLED_EMAIL", "")     # email used when registering with ACLED
NEWS_API_KEY  = os.environ.get("NEWS_API_KEY", "")    # newsapi.org — free tier (100 req/day)

# === MISC ===
ANNUALIZATION_FACTOR = 52  # Weekly to annual
