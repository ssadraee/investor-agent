"""
Market Scanner — Collects price data, macro indicators, volatility, and produces
a structured market state representation.
"""
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import logging
import json

from agent.config import (
    UNIVERSE, LOOKBACK_DAYS, SHORT_LOOKBACK, FRED_API_KEY, FRED_SERIES,
    EQUITY_TICKERS, BOND_TICKERS, ALT_TICKERS, BENCHMARK_TICKER
)

logger = logging.getLogger(__name__)


def fetch_prices(tickers=None, period_days=None):
    """Fetch historical prices for universe. Returns DataFrame of adjusted close."""
    if tickers is None:
        tickers = list(UNIVERSE.keys())
    if period_days is None:
        period_days = LOOKBACK_DAYS

    end = datetime.now()
    start = end - timedelta(days=period_days + 10)  # buffer for weekends

    all_tickers = tickers + ["^VIX", "^TNX", "^FVX", "^IRX"]
    unique_tickers = list(set(all_tickers))

    logger.info(f"Fetching prices for {len(unique_tickers)} tickers...")
    try:
        data = yf.download(unique_tickers, start=start.strftime("%Y-%m-%d"),
                           end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"]
        else:
            prices = data[["Close"]].rename(columns={"Close": unique_tickers[0]})
        prices = prices.dropna(how="all").ffill()
        logger.info(f"Fetched {len(prices)} days of data")
        return prices
    except Exception as e:
        logger.error(f"Price fetch failed: {e}")
        return pd.DataFrame()


def fetch_fred_data():
    """Fetch macro data from FRED. Returns dict of latest values."""
    if not FRED_API_KEY:
        logger.warning("No FRED API key — skipping macro data")
        return {}

    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        macro = {}
        for series_id, name in FRED_SERIES.items():
            try:
                data = fred.get_series(series_id, observation_start=(datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
                if data is not None and len(data) > 0:
                    macro[series_id] = {
                        "name": name,
                        "latest": float(data.iloc[-1]),
                        "prev": float(data.iloc[-2]) if len(data) > 1 else None,
                        "change": float(data.iloc[-1] - data.iloc[-2]) if len(data) > 1 else 0,
                    }
            except Exception as e:
                logger.warning(f"FRED series {series_id} failed: {e}")
        return macro
    except ImportError:
        logger.warning("fredapi not installed — skipping FRED data")
        return {}


def fetch_global_market_data():
    """Fetch regional equity indices, FX pairs, and commodity futures via yfinance."""
    from agent.config import REGIONAL_INDICES, FX_TICKERS, COMMODITY_TICKERS

    all_tickers = list(REGIONAL_INDICES.keys()) + list(FX_TICKERS.keys()) + list(COMMODITY_TICKERS.keys())
    end = datetime.now()
    start = end - timedelta(days=LOOKBACK_DAYS + 10)

    logger.info(f"Fetching global market data: {len(all_tickers)} tickers...")
    try:
        data = yf.download(all_tickers, start=start.strftime("%Y-%m-%d"),
                           end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"]
        else:
            prices = data[["Close"]].rename(columns={"Close": all_tickers[0]})
        prices = prices.dropna(how="all").ffill()
        logger.info(f"Global data: {len(prices)} days, {prices.shape[1]} series")
        return prices
    except Exception as e:
        logger.error(f"Global market data fetch failed: {e}")
        return pd.DataFrame()


def fetch_global_fred_data():
    """Fetch international macro, credit spreads, and EPU data from FRED."""
    from agent.config import FRED_SERIES_GLOBAL

    if not FRED_API_KEY:
        logger.warning("No FRED API key — skipping global FRED data")
        return {}

    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        macro = {}
        for series_id, name in FRED_SERIES_GLOBAL.items():
            try:
                data = fred.get_series(series_id, observation_start=(datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
                if data is not None and len(data) > 0:
                    macro[series_id] = {
                        "name": name,
                        "latest": float(data.iloc[-1]),
                        "prev": float(data.iloc[-2]) if len(data) > 1 else None,
                        "change": float(data.iloc[-1] - data.iloc[-2]) if len(data) > 1 else 0,
                    }
            except Exception as e:
                logger.warning(f"Global FRED series {series_id} failed: {e}")
        logger.info(f"Global FRED data: {len(macro)}/{len(FRED_SERIES_GLOBAL)} series fetched")
        return macro
    except ImportError:
        logger.warning("fredapi not installed — skipping global FRED data")
        return {}


def compute_market_signals(prices):
    """Compute derived signals from price data."""
    signals = {}
    tickers = [t for t in UNIVERSE.keys() if t in prices.columns]

    if len(tickers) == 0:
        return signals

    returns = prices[tickers].pct_change().dropna()
    if len(returns) < 5:
        return signals

    # --- VIX ---
    if "^VIX" in prices.columns:
        vix_series = prices["^VIX"].dropna()
        signals["vix_current"] = float(vix_series.iloc[-1]) if len(vix_series) > 0 else 20.0
        signals["vix_ma20"] = float(vix_series.tail(20).mean()) if len(vix_series) >= 20 else signals["vix_current"]
        signals["vix_percentile"] = float((vix_series.iloc[-1] - vix_series.min()) / (vix_series.max() - vix_series.min())) if len(vix_series) > 1 else 0.5
    else:
        signals["vix_current"] = 20.0
        signals["vix_ma20"] = 20.0
        signals["vix_percentile"] = 0.5

    # --- Yield curve (10Y - 2Y proxy) ---
    if "^TNX" in prices.columns and "^FVX" in prices.columns:
        tnx = prices["^TNX"].dropna()
        fvx = prices["^FVX"].dropna()
        if len(tnx) > 0 and len(fvx) > 0:
            signals["yield_spread"] = float(tnx.iloc[-1] - fvx.iloc[-1])
        else:
            signals["yield_spread"] = 0.0
    else:
        signals["yield_spread"] = 0.0

    # --- Broad market momentum ---
    if BENCHMARK_TICKER in prices.columns:
        spy = prices[BENCHMARK_TICKER].dropna()
        if len(spy) >= SHORT_LOOKBACK:
            signals["spy_momentum_63d"] = float(spy.iloc[-1] / spy.iloc[-SHORT_LOOKBACK] - 1)
        else:
            signals["spy_momentum_63d"] = 0.0
        if len(spy) >= 21:
            signals["spy_momentum_21d"] = float(spy.iloc[-1] / spy.iloc[-21] - 1)
        else:
            signals["spy_momentum_21d"] = 0.0
    else:
        signals["spy_momentum_63d"] = 0.0
        signals["spy_momentum_21d"] = 0.0

    # --- Sector momentum ---
    sector_mom = {}
    for t in tickers:
        series = prices[t].dropna()
        if len(series) >= SHORT_LOOKBACK:
            sector_mom[t] = float(series.iloc[-1] / series.iloc[-SHORT_LOOKBACK] - 1)
    signals["sector_momentum"] = sector_mom

    # --- Cross-asset signals ---
    equity_rets = returns[[t for t in EQUITY_TICKERS if t in returns.columns]]
    bond_rets = returns[[t for t in BOND_TICKERS if t in returns.columns]]

    if len(equity_rets.columns) > 0 and len(equity_rets) >= 5:
        signals["equity_avg_return_5d"] = float(equity_rets.tail(5).mean().mean())
        signals["equity_volatility_21d"] = float(equity_rets.tail(21).std().mean() * np.sqrt(252)) if len(equity_rets) >= 21 else 0.15
    else:
        signals["equity_avg_return_5d"] = 0.0
        signals["equity_volatility_21d"] = 0.15

    if len(bond_rets.columns) > 0 and len(bond_rets) >= 5:
        signals["bond_avg_return_5d"] = float(bond_rets.tail(5).mean().mean())
    else:
        signals["bond_avg_return_5d"] = 0.0

    # --- Correlation regime ---
    if len(equity_rets.columns) > 0 and len(bond_rets.columns) > 0 and len(returns) >= 21:
        eq_mean = equity_rets.tail(21).mean(axis=1)
        bd_mean = bond_rets.tail(21).mean(axis=1)
        if len(eq_mean) > 5 and len(bd_mean) > 5:
            signals["equity_bond_corr_21d"] = float(eq_mean.corr(bd_mean))
        else:
            signals["equity_bond_corr_21d"] = -0.3
    else:
        signals["equity_bond_corr_21d"] = -0.3

    # --- Market breadth ---
    if len(equity_rets.columns) > 0 and len(equity_rets) >= 5:
        weekly_ret = equity_rets.tail(5).sum()
        signals["breadth_positive"] = float((weekly_ret > 0).sum() / len(weekly_ret))
    else:
        signals["breadth_positive"] = 0.5

    # --- Realized vol vs implied vol ---
    if BENCHMARK_TICKER in returns.columns and len(returns) >= 21:
        realized_vol = float(returns[BENCHMARK_TICKER].tail(21).std() * np.sqrt(252) * 100)
        signals["vol_risk_premium"] = signals["vix_current"] - realized_vol
    else:
        signals["vol_risk_premium"] = 0.0

    return signals


def compute_regional_signals(global_prices):
    """Compute momentum, volatility, and breadth signals for global equity regions."""
    from agent.config import REGIONAL_INDICES

    signals = {}
    if global_prices.empty:
        return signals

    available = [t for t in REGIONAL_INDICES if t in global_prices.columns]
    if not available:
        return signals

    momentum_21d, momentum_63d, vol_21d = {}, {}, {}
    for ticker in available:
        series = global_prices[ticker].dropna()
        if len(series) >= 21:
            momentum_21d[ticker] = float(series.iloc[-1] / series.iloc[-21] - 1)
        if len(series) >= SHORT_LOOKBACK:
            momentum_63d[ticker] = float(series.iloc[-1] / series.iloc[-SHORT_LOOKBACK] - 1)
        if len(series) >= 22:
            vol_21d[ticker] = float(series.pct_change().dropna().tail(21).std() * np.sqrt(252))

    signals["regional_momentum_21d"] = momentum_21d
    signals["regional_momentum_63d"] = momentum_63d
    signals["regional_volatility_21d"] = vol_21d

    if momentum_21d:
        vals = list(momentum_21d.values())
        signals["global_breadth_21d"] = float(sum(v > 0 for v in vals) / len(vals))
        signals["regional_divergence_21d"] = float(np.std(vals))

    # Europe composite
    eu = ["^STOXX50E", "^GDAXI", "^FTSE", "^FCHI"]
    eu_moms = [momentum_21d[t] for t in eu if t in momentum_21d]
    if eu_moms:
        signals["europe_composite_momentum_21d"] = float(np.mean(eu_moms))

    # APAC composite
    apac = ["^N225", "^HSI", "^AXJO", "^BSESN", "000001.SS"]
    apac_moms = [momentum_21d[t] for t in apac if t in momentum_21d]
    if apac_moms:
        signals["apac_composite_momentum_21d"] = float(np.mean(apac_moms))

    # EM equity stress
    em = ["^BVSP", "^BSESN", "000001.SS", "^HSI", "^MXX"]
    em_moms = [momentum_21d[t] for t in em if t in momentum_21d]
    if em_moms:
        signals["em_equity_momentum_21d"] = float(np.mean(em_moms))

    return signals


def compute_fx_signals(global_prices):
    """Compute USD strength, EM currency stress, and safe-haven demand from FX pairs."""
    from agent.config import FX_TICKERS

    signals = {}
    if global_prices.empty:
        return signals

    available = [t for t in FX_TICKERS if t in global_prices.columns]
    if not available:
        return signals

    fx_mom_21d = {}
    for ticker in available:
        series = global_prices[ticker].dropna()
        if len(series) >= 21:
            fx_mom_21d[ticker] = float(series.iloc[-1] / series.iloc[-21] - 1)

    signals["fx_momentum_21d"] = fx_mom_21d

    # USD basket strength: EUR/GBP fall vs USD = USD strong; USD/JPY, USD/CNY rise = USD strong
    usd_components = []
    if "EURUSD=X" in fx_mom_21d:
        usd_components.append(-fx_mom_21d["EURUSD=X"])
    if "GBPUSD=X" in fx_mom_21d:
        usd_components.append(-fx_mom_21d["GBPUSD=X"])
    if "USDJPY=X" in fx_mom_21d:
        usd_components.append(fx_mom_21d["USDJPY=X"])
    if "USDCNY=X" in fx_mom_21d:
        usd_components.append(fx_mom_21d["USDCNY=X"])
    if usd_components:
        signals["usd_basket_strength_21d"] = float(np.mean(usd_components))

    # EM FX stress: USD appreciating vs EM currencies = pressure on EM assets
    em_stress = [fx_mom_21d[t] for t in ["USDBRL=X", "USDINR=X", "USDCNY=X"] if t in fx_mom_21d]
    if em_stress:
        signals["em_fx_stress_21d"] = float(np.mean(em_stress))

    # Safe-haven demand: JPY and CHF strengthening (USD/JPY and USD/CHF falling)
    sh = []
    if "USDJPY=X" in fx_mom_21d:
        sh.append(-fx_mom_21d["USDJPY=X"])
    if "USDCHF=X" in fx_mom_21d:
        sh.append(-fx_mom_21d["USDCHF=X"])
    if sh:
        signals["safe_haven_demand_21d"] = float(np.mean(sh))

    # AUD/JPY as risk-on/off barometer (positive = risk appetite)
    if "AUDUSD=X" in fx_mom_21d and "USDJPY=X" in fx_mom_21d:
        signals["audjpy_risk_signal_21d"] = float(fx_mom_21d["AUDUSD=X"] + fx_mom_21d["USDJPY=X"])

    # CNY depreciation as China-specific stress proxy
    if "USDCNY=X" in fx_mom_21d:
        signals["cny_depreciation_21d"] = float(fx_mom_21d["USDCNY=X"])

    return signals


def compute_commodity_signals(global_prices):
    """Compute oil regime, copper/gold growth signal, and broad commodity pressure."""
    signals = {}
    if global_prices.empty:
        return signals

    def _series(ticker):
        if ticker in global_prices.columns:
            s = global_prices[ticker].dropna()
            return s if len(s) > 0 else None
        return None

    # Oil: trend, volatility, z-score spike detector
    oil = _series("CL=F") or _series("BZ=F")
    if oil is not None and len(oil) >= 21:
        oil_rets = oil.pct_change().dropna()
        signals["oil_trend_21d"] = float(oil.iloc[-1] / oil.iloc[-21] - 1)
        signals["oil_volatility_21d"] = float(oil_rets.tail(21).std() * np.sqrt(252))
        if len(oil) >= SHORT_LOOKBACK:
            signals["oil_trend_63d"] = float(oil.iloc[-1] / oil.iloc[-SHORT_LOOKBACK] - 1)
        ma20 = float(oil.tail(20).mean())
        std20 = float(oil.tail(20).std())
        signals["oil_zscore_20d"] = float((oil.iloc[-1] - ma20) / std20) if std20 > 0 else 0.0

    # Brent–WTI spread: widens on supply disruptions / geopolitical premiums
    brent, wti = _series("BZ=F"), _series("CL=F")
    if brent is not None and wti is not None:
        signals["brent_wti_spread"] = float(brent.iloc[-1] - wti.iloc[-1])

    # Copper/Gold ratio: rising = growth optimism; falling = risk-off / recession fear
    copper, gold = _series("HG=F"), _series("GC=F")
    if copper is not None and gold is not None:
        aligned = pd.DataFrame({"copper": copper, "gold": gold}).dropna()
        if len(aligned) >= 21:
            ratio_now = float(aligned["copper"].iloc[-1] / aligned["gold"].iloc[-1])
            ratio_21d_ago = float(aligned["copper"].iloc[-21] / aligned["gold"].iloc[-21])
            signals["copper_gold_ratio"] = ratio_now
            signals["copper_gold_trend_21d"] = float(ratio_now / ratio_21d_ago - 1)

    # Natural gas: European energy / supply-chain stress proxy
    natgas = _series("NG=F")
    if natgas is not None and len(natgas) >= 21:
        signals["natgas_volatility_21d"] = float(natgas.pct_change().dropna().tail(21).std() * np.sqrt(252))
        signals["natgas_trend_21d"] = float(natgas.iloc[-1] / natgas.iloc[-21] - 1)

    # Broad commodity inflation pressure (equal-weighted basket)
    basket_rets = []
    for t in ["CL=F", "BZ=F", "HG=F", "GC=F", "ZW=F"]:
        s = _series(t)
        if s is not None and len(s) >= 21:
            basket_rets.append(float(s.iloc[-1] / s.iloc[-21] - 1))
    if basket_rets:
        signals["broad_commodity_momentum_21d"] = float(np.mean(basket_rets))

    return signals


def compute_geopolitical_proxy_signals(macro_global):
    """
    Derive geopolitical and political risk proxies from financial stress indicators.

    Uses:
    - US Economic Policy Uncertainty index (USEPUINDXD) via FRED
    - Credit spreads: US HY, US IG, EM Corp OAS via FRED
    - International bond yields for rate-policy divergence

    For direct political/conflict data see PROPOSED_ADDITIONAL_SOURCES in config.py.
    """
    signals = {}
    if not macro_global:
        return signals

    def _get(series_id):
        return macro_global.get(series_id)

    # Economic Policy Uncertainty
    epu = _get("USEPUINDXD")
    if epu:
        signals["us_epu_level"] = epu["latest"]
        signals["us_epu_change"] = epu["change"]
        signals["us_epu_elevated"] = bool(epu["latest"] > 200)

    # US High Yield spreads (systemic credit/political stress)
    hy = _get("BAMLH0A0HYM2")
    if hy:
        signals["us_hy_spread_bp"] = hy["latest"]
        signals["us_hy_spread_change_bp"] = hy["change"]
        signals["credit_stress_flag"] = bool(hy["latest"] > 500)

    # EM credit spreads (emerging market political/economic risk)
    em = _get("BAMLEMCBPIOAS")
    if em:
        signals["em_credit_spread_bp"] = em["latest"]
        signals["em_credit_spread_change_bp"] = em["change"]
        signals["em_credit_stress_flag"] = bool(em["latest"] > 400)

    # US IG spreads
    ig = _get("BAMLC0A0CM")
    if ig:
        signals["us_ig_spread_bp"] = ig["latest"]
        signals["us_ig_spread_change_bp"] = ig["change"]

    # International yields (rate-policy divergence signals)
    for key, label in [("IRLTLT01EZM156N", "ea"), ("IRLTLT01JPM156N", "japan"), ("IRLTLT01GBM156N", "uk")]:
        entry = _get(key)
        if entry:
            signals[f"{label}_10y_yield"] = entry["latest"]
            signals[f"{label}_10y_yield_change"] = entry["change"]

    # Composite financial stress score (0–1; higher = more stress)
    stress_parts = []
    if epu:
        stress_parts.append(min(epu["latest"] / 400.0, 1.0))
    if hy:
        stress_parts.append(min(hy["latest"] / 1000.0, 1.0))
    if em:
        stress_parts.append(min(em["latest"] / 600.0, 1.0))
    if stress_parts:
        signals["composite_financial_stress"] = float(np.mean(stress_parts))

    return signals


def compute_return_covariance(prices, tickers=None, halflife=None):
    """Compute EWMA covariance matrix for allocation."""
    from agent.config import EWMA_HALFLIFE
    if halflife is None:
        halflife = EWMA_HALFLIFE
    if tickers is None:
        tickers = [t for t in UNIVERSE.keys() if t in prices.columns]

    returns = prices[tickers].pct_change().dropna()
    if len(returns) < 10:
        return pd.DataFrame(np.eye(len(tickers)) * 0.04, index=tickers, columns=tickers), returns

    ewma_cov = returns.ewm(halflife=halflife).cov()
    last_date = returns.index[-1]
    cov_matrix = ewma_cov.loc[last_date]
    return cov_matrix, returns


def scan_market():
    """Main scan function. Returns structured market state dict."""
    logger.info("=== MARKET SCAN START ===")

    prices = fetch_prices()
    if prices.empty:
        logger.error("No price data available")
        return {"error": "no_data", "timestamp": datetime.now().isoformat()}

    signals = compute_market_signals(prices)
    macro = fetch_fred_data()

    # --- Global expansion: regional indices, FX, commodities, international macro ---
    global_prices = fetch_global_market_data()
    macro_global = fetch_global_fred_data()

    regional_signals = compute_regional_signals(global_prices)
    fx_signals = compute_fx_signals(global_prices)
    commodity_signals = compute_commodity_signals(global_prices)
    geopolitical_proxy_signals = compute_geopolitical_proxy_signals(macro_global)

    # --- External data sources (World Bank, IMF, OECD, GDELT, ECB, ACLED, NewsAPI) ---
    from agent.datasources import fetch_external_sources
    external_sources = fetch_external_sources()

    tickers = [t for t in UNIVERSE.keys() if t in prices.columns]
    cov_matrix, returns = compute_return_covariance(prices, tickers)

    # Expected returns (simple momentum-based estimate)
    expected_returns = {}
    for t in tickers:
        if t in prices.columns:
            series = prices[t].dropna()
            if len(series) >= SHORT_LOOKBACK:
                mom = series.iloc[-1] / series.iloc[-SHORT_LOOKBACK] - 1
                expected_returns[t] = mom / (SHORT_LOOKBACK / 252)  # Annualize
            else:
                expected_returns[t] = 0.0

    state = {
        "timestamp": datetime.now().isoformat(),
        "available_tickers": tickers,
        "signals": signals,
        "macro": macro,
        "macro_global": macro_global,
        "regional_signals": regional_signals,
        "fx_signals": fx_signals,
        "commodity_signals": commodity_signals,
        "geopolitical_proxy_signals": geopolitical_proxy_signals,
        "external_sources": external_sources,
        "expected_returns": expected_returns,
        "covariance_available": len(cov_matrix) > 0,
        "data_quality": {
            "tickers_fetched": len(tickers),
            "tickers_requested": len(UNIVERSE),
            "days_of_data": len(prices),
            "global_tickers_fetched": global_prices.shape[1] if not global_prices.empty else 0,
            "global_fred_series_fetched": len(macro_global),
            "external_sources_ok": sum(1 for v in external_sources.values() if v),
        }
    }

    breadth = regional_signals.get("global_breadth_21d")
    breadth_str = f", global breadth={breadth:.0%}" if breadth is not None else ""
    logger.info(f"Scan complete: {len(tickers)} tickers, VIX={signals.get('vix_current', 'N/A')}{breadth_str}")
    return state
