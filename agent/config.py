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
EQUITY_TICKERS = ["SPY", "QQQ", "IWM", "EFA", "VWO", "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU"]
BOND_TICKERS = ["TLT", "IEF", "AGG", "LQD"]
ALT_TICKERS = ["GLD", "VNQ", "DBC"]

# === LEARNING PARAMETERS ===
LEARNING_RATE = 0.1
FORGETTING_FACTOR = 0.95
MIN_WEEKS_BEFORE_DRIFT = 8       # Weeks before weights can deviate >20%
MAX_WEIGHT_DEVIATION = 0.20      # Max deviation from prior

# === SIGNAL NAMES ===
SIGNALS = [
    "momentum",
    "mean_reversion",
    "volatility_regime",
    "macro_trend",
    "yield_curve",
    "cross_asset_momentum",
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

# === PATHS ===
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "agent.db")
DOCS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
HISTORY_PATH = os.path.join(DOCS_PATH, "history")

# === EMAIL ===
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# === MISC ===
ANNUALIZATION_FACTOR = 52  # Weekly to annual
